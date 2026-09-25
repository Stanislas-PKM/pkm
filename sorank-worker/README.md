# Connexion SoRank : blog automatique sur vincentcoachpoker.com

SoRank envoie chaque article via un webhook (requête POST). Un site GitHub
Pages est statique et ne peut pas recevoir de POST, il faut donc un petit
relais entre les deux. C'est le rôle du fichier `worker.js` de ce dossier,
à déployer sur **Cloudflare Workers** (gratuit).

## Comment ça marche

```
SoRank ──POST──> Worker Cloudflare ──dépose le JSON──> blog/_queue/ (dépôt GitHub)
                                                            │
                              GitHub Actions "Publication SoRank" se déclenche
                                                            │
                         génère blog/<slug>/index.html + index du blog + sitemap
                                                            │
                                    GitHub Pages redéploie le site (~2 min)
```

Chaque article publié depuis SoRank apparaît sur
`https://vincentcoachpoker.com/blog/<slug>/`, dans le design du site.
Les mises à jour envoyées depuis SoRank ("Envoyer la mise à jour de
l'article") remplacent l'article existant, sans jamais créer de doublon.

## Mise en place (une seule fois, ~10 minutes)

### 1. Créer un token GitHub

1. Va sur https://github.com/settings/personal-access-tokens/new
2. Token name : `sorank-worker` · Expiration : 1 an (mets un rappel)
3. Repository access : **Only select repositories** → `Stanislas-PKM/pkm`
4. Permissions → Repository permissions → **Contents : Read and write**
5. Génère le token et copie-le (il ne sera plus affiché ensuite).

### 2. Déployer le worker sur Cloudflare

1. Crée un compte gratuit sur https://dash.cloudflare.com
2. Menu **Workers & Pages** → **Create** → **Create Worker**
3. Nomme-le `sorank-relay` → **Deploy**
4. Clique **Edit code**, remplace tout le contenu par celui de `worker.js`,
   puis **Deploy**.
5. Reviens sur la page du worker → **Settings** → **Variables and Secrets** :
   - `SORANK_SECRET` (type **Secret**) : invente une longue chaîne aléatoire
     (30+ caractères), garde-la pour l'étape 3
   - `GITHUB_TOKEN` (type **Secret**) : le token GitHub de l'étape 1
   - `GITHUB_REPO` (type Text) : `Stanislas-PKM/pkm`
   - `SITE_ORIGIN` (type Text) : `https://vincentcoachpoker.com`
6. Note l'URL du worker, du type
   `https://sorank-relay.<ton-compte>.workers.dev`

### 3. Connecter SoRank

1. Dans SoRank : **Paramètres** → **Plateformes de publication** → carte
   **Webhook** → **Connect your website**
2. **Webhook URL** : l'URL du worker (étape 2.6)
3. **Secret token** : la même chaîne que `SORANK_SECRET`
4. Clique **Test** : SoRank doit afficher un succès (le worker répond au
   contrat version 2 avec les capacités `article.published` et
   `article.updated`)
5. Clique **Save webhook**

### 4. Publier un premier article

Publie un article depuis SoRank : il apparaît sur
`https://vincentcoachpoker.com/blog/` environ 2 à 3 minutes plus tard.
SoRank confirme ensuite la publication tout seul (il vérifie la balise
`sorank-operation-id` présente sur la page générée) et affiche « Publié »
avec le lien.

## En cas de problème

- **Le Test SoRank échoue** : vérifie que le Secret token dans SoRank est
  strictement identique à `SORANK_SECRET` dans Cloudflare.
- **L'article n'apparaît pas** : regarde l'onglet
  [Actions du dépôt](https://github.com/Stanislas-PKM/pkm/actions) — le
  workflow « Publication SoRank » doit s'être exécuté en vert. S'il est
  rouge, ouvre-le et envoie les logs à Claude.
- **Erreur 500 côté worker** : le token GitHub a probablement expiré ou n'a
  pas la permission Contents en écriture — régénère-le (étape 1) et mets à
  jour le secret `GITHUB_TOKEN` du worker.
