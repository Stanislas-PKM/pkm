/**
 * Relais webhook SoRank -> GitHub pour vincentcoachpoker.com
 *
 * A deployer sur Cloudflare Workers (voir README.md a cote).
 *
 * Role : GitHub Pages est un site statique et ne peut pas recevoir de
 * requete POST. Ce worker recoit le webhook SoRank, repond au contrat
 * version 2, et depose la charge utile dans blog/_queue/ du depot GitHub.
 * Le workflow "Publication SoRank" prend ensuite le relais pour generer
 * la page de l'article et redeployer le site.
 *
 * Variables a configurer sur le worker :
 *   SORANK_SECRET (secret)  : jeton partage avec SoRank (champ "Secret token")
 *   GITHUB_TOKEN  (secret)  : PAT fine-grained, depot pkm, Contents: Read/Write
 *   GITHUB_REPO   (variable): "Stanislas-PKM/pkm"
 *   SITE_ORIGIN   (variable): "https://vincentcoachpoker.com"
 */

function json(body, status) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

// base64 d'une chaine UTF-8, par blocs pour eviter les limites de pile
function b64(str) {
  const bytes = new TextEncoder().encode(str);
  let bin = "";
  const chunk = 8192;
  for (let i = 0; i < bytes.length; i += chunk) {
    bin += String.fromCharCode(...bytes.subarray(i, i + chunk));
  }
  return btoa(bin);
}

export default {
  async fetch(request, env) {
    if (request.method !== "POST") {
      return new Response("Method Not Allowed", { status: 405 });
    }

    // Verifie que l'appel vient bien de SoRank (jeton Bearer)
    const auth = request.headers.get("Authorization") || "";
    if (!env.SORANK_SECRET || auth !== `Bearer ${env.SORANK_SECRET}`) {
      return new Response("Unauthorized", { status: 401 });
    }

    let payload;
    try {
      payload = await request.json();
    } catch {
      return json({ error: "invalid JSON" }, 400);
    }

    const event = payload.event;

    // Test de connectivite : on declare le contrat v2, sans rien publier
    if (event === "webhook.test") {
      return json(
        {
          sorank_webhook_version: 2,
          capabilities: ["article.published", "article.updated"],
        },
        200
      );
    }

    if (event !== "article.published" && event !== "article.updated") {
      return json({ error: `unknown event: ${event}` }, 400);
    }

    const article = payload.article;
    if (!article || !article.id) {
      return json({ error: "missing article" }, 400);
    }

    const record = {
      event,
      idempotency_key:
        request.headers.get("Idempotency-Key") || payload.delivery_id || "",
      revision: request.headers.get("X-Sorank-Article-Revision") || "",
      delivery_id: payload.delivery_id || "",
      received_at: new Date().toISOString(),
      article,
    };

    // Depose la livraison dans blog/_queue/ du depot : ce commit declenche
    // le workflow GitHub Actions qui publie reellement l'article.
    const stamp = record.received_at.replace(/[:.]/g, "-");
    const path = `blog/_queue/${stamp}-${String(article.id).slice(0, 12)}.json`;
    const res = await fetch(
      `https://api.github.com/repos/${env.GITHUB_REPO}/contents/${path}`,
      {
        method: "PUT",
        headers: {
          Authorization: `Bearer ${env.GITHUB_TOKEN}`,
          Accept: "application/vnd.github+json",
          "X-GitHub-Api-Version": "2022-11-28",
          "User-Agent": "sorank-relay-worker",
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          message: `File d'attente SoRank : ${event} (${article.slug || article.id})`,
          content: b64(JSON.stringify(record, null, 2)),
          branch: "main",
        }),
      }
    );

    if (!res.ok) {
      const detail = await res.text();
      console.log(`GitHub API ${res.status}: ${detail.slice(0, 500)}`);
      return json({ error: "failed to queue article" }, 500);
    }

    // Publication asynchrone : 202 "accepted". SoRank confirmera ensuite en
    // trouvant <meta name="sorank-operation-id"> sur la page publiee.
    const body = { sorank_webhook_version: 2, status: "accepted" };
    if (event === "article.published" && article.slug) {
      body.article_url = `${env.SITE_ORIGIN}/blog/${article.slug}/`;
    }
    return json(body, 202);
  },
};
