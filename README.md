# Vincent Coach Poker — site statique

Site HTML/CSS pur, sans build ni dépendance. Hébergeable tel quel sur GitHub Pages.

## Structure

    index.html                  ->  /
    mon-parcours/index.html     ->  /mon-parcours
    la-salle-du-temps/index.html->  /la-salle-du-temps
    cgv/index.html              ->  /cgv
    mentions-legales/index.html ->  /mentions-legales
    404.html                    ->  page d'erreur
    assets/style.css            ->  feuille de style unique
    assets/img/                 ->  images (à déposer)
    .nojekyll                   ->  désactive Jekyll sur GitHub Pages

## Images à déposer dans assets/img/

- `poker-table.jpg`      (hero)
- `poker-community.jpg`  (section accompagnement)
- `vincent.jpg`          (portrait)

Récupérables depuis le site Lovable actuel, dossier /assets/.

## Mise en ligne

1. Créer un dépôt GitHub, y pousser ces fichiers à la racine.
2. Settings > Pages > Source : « Deploy from a branch », branche `main`, dossier `/ (root)`.
3. Attendre ~1 minute.

## Formulaire

GitHub Pages est un hébergement statique : aucun script serveur ne tourne.
Le formulaire d'inscription doit pointer vers un service externe
(Formspree, Brevo, systeme.io, ConvertKit...). Voir l'attribut `action`
du `<form>` dans `index.html`.
