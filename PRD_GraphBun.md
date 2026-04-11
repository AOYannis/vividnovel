L'objectif du projet est de créer un jeu interactif très simple pour adulte au format "livre dont vous êtes le héros" de séduction, basé sur une orchestration / génération de l'histoire par Grok, et une génération d'image par Z Image turbo (et éventuellement P Video par pruna.)

Le déroulé est le suivant : lorsque le joueur clique sur "démarrer" il voit une série de choix prédéfinis et une option "libre" à chaque fois : 
- Donner son prénom, son âge,genre auquel il s'identifie, préférences amoureuses 
- Contexte avec deux choix : endroit (Paris, une ville, un ) A contemporain en 2026 , B époque années 1800, C futur années 2100 

L'histoire démarre alors. La narration se fait à la 2eme personne "tu prend ton téléphone sous le canapé et te décide à sortir..." et une séquence d'images (5) est générée, 


Phase 1: interface de test des modeles (les parametres du modeles Z image, yc image reference, lora multiples , steps... toutes les configs possibles) et les parametres du modele video (idem mais focus sur P Video, avec possibilité de prendre en image de référence l'image générée par Z image), prompts pour chacun, seed etc.

L'historique des images générées est navigable, d'anciennes images peut etre sélectionnées pour être en entrée de la vidéo.. 

Le prompt lui même peut etre généré par Grok.

Phase 2 : une entrée dans le menu permet de tester le jeu réellement : l'objectif principal est de gérer : 
- le casting (choisir deux "acteurs" qui lorsqu'ils apparaissent à l'image). Lorsque ces personnages apparaissent, le lora concerné est inclus dans les parametres de génération d'image car ils assurent la cohérence. Un mot clé "trigger word" existe pour chacun de ces acteurs/actrices
- la cohérence de l'image générée par rapport à l'histoire, et par rapport à l'état précédent (par exemple, si le lieu de l'image 1 est un restaurant, et que l'histoire les fait passer à un autre plat, le prompt doit de nouveau décrire le restaurant ; inversement, sortir )
- idem pour la cohérence des habits; si elle change apres l'image 3, et qu'aucune raison qu'elle change en image 4, la description sur image 4 devra etre copiée et identique sur image 4. Si en revanche l'acteur enlève un habit, manteau, etc. elle restera sans ce manteau par la suite.  
- style cinématographique même si on reste en POV tout le temps (mais cela signifie que les personnages ne regardent pas forcément le joueur tout le temps) 

/Users/yannis.achour/dev/20260319_RunwV2/runware-dev-guide.md référence l'utilisation des modeles de génération d'images

/Users/yannis.achour/dev/20260319_RunwV2/Grok documentation and model pricing a des infos sur l'usage Grok

L'objectif est de géréer les temps de génération d'image, ainsi que les délais pour grok, pour donner l'impression la plus fluide au joueur : 

- par exemple, streamer la génération de l'histoire, et demander à l'agent de lancer de préciser le prompt de l'image à générer pour décrire l'histoire au moment ou il a lieu dans la narration -> Immédiatement lancer un appel de fonction de génération ; de sorte, pendant que l'utilisateur lit l'histoire associée à l'image 1, la suivante est en train de se générér, etc. etc.  ; les images prennent environ 6 secondes a se générer, et les vidéos environs 50

Après 5 images, un choix est proposé à l'utilisateur pour la suite. 

Afin de débuguer, le prompt lui même de l'agent qui va faire cette orchestration peut etre modifié par l'utilisateur, et il peut demander à grok de le changer selon ses instructions.

Je souhaiterai aussi avoir un log / feedback détaillé sur les coûts / apres chaque sequence par exmple, avec la décomposition tokens entrant grok, generation d'image, etc.à

Donc : but = le plus rapide posssible pour afficher l'image suivante

 Architecture : Pipeline Streaming + Function Calling

  Le concept clé : Grok streame la narration et appelle une fonction
  generate_scene_image à chaque moment clé. Le backend intercepte
  chaque appel mid-stream et lance immédiatement la génération
  d'image Runware. Pendant que le joueur lit le texte de la scène N,
  l'image N+1 est déjà en train de se générer.

  Temps   Grok Stream                   Runware              Frontend
  ───────────────────────────────────────────────────────────────────
  ──
  0s      Narration scène 0...          -                    Texte
  apparaît
  ~2s     ⚡ tool_call: image 0         → Image 0 start
  "Chargement..."
  ~5s     Narration scène 0 (suite)     Image 0 gen...       Joueur
  lit
  ~8s     ⚡ tool_call: image 1         Image 0 READY ✓      Image 0
  s'affiche
                                        → Image 1 start      Joueur
  regarde img 0
  ~14s    ⚡ tool_call: image 2         Image 1 READY ✓      Image 1
  s'affiche
                                        → Image 2 start      ...ainsi
   de suite

  Résultat : le joueur ne voit quasiment jamais de chargement.

  ---
  Stack technique

  frontend/  (Vite + React + TypeScript + Zustand + Tailwind)
  ├── src/
  │   ├── stores/gameStore.ts          # État global (joueur, cast,
  séquences, coûts)
  │   ├── hooks/useStoryStream.ts      # Consomme le SSE, met à jour
  le store
  │   ├── api/client.ts                # Fetch + SSE helpers
  │   ├── components/
  │   │   ├── setup/                   # PlayerForm, SettingPicker,
  CastPicker
  │   │   ├── story/                   # StoryViewer, NarrationPanel,
   SceneImage, ChoicePanel
  │   │   └── debug/                   # SystemPromptEditor, CostLog,
   GeneratedPrompts
  │   └── pages/
  │       ├── SetupPage.tsx            # Wizard en 3 étapes
  │       └── GamePage.tsx             # Expérience de jeu

  backend/  (FastAPI)
  ├── config.py
  ├── main.py
  ├── services/
  │   ├── story_engine.py              # Orchestration : boucle Grok
  stream + fire image tasks
  │   ├── runware_service.py           # Génération image avec LoRA +
   trigger words
  │   ├── grok_service.py              # Client Grok streaming
  │   ├── prompt_builder.py            # Construit le system prompt
  dynamiquement
  │   └── consistency_tracker.py       # Suit location, vêtements,
  état de chaque acteur
  ├── routes/
  │   ├── game.py                      # POST /api/game/sequence
  (SSE)
  │   └── debug.py                     # System prompt editor, coûts
  └── tools/
      └── scene_image_tool.py          # Schéma function calling Grok

  ---
  Function Calling Grok : generate_scene_image

  Grok reçoit un outil avec ce schéma :

  {
      "name": "generate_scene_image",
      "parameters": {
          "image_index":        int,       # 0-4
          "image_prompt":       str,       # prompt détaillé 80-200
  mots pour Z-Image
          "actors_present":     [str],     # ["milena",
  "shorty_asian"]
          "location_description": str,     # "restaurant parisien,
  bougies" — identique si inchangé
          "clothing_state":     {str: str} # {"milena": "robe noire
  en soie"} — cohérent image à image
      }
  }

  Le backend :
  1. Intercepte le tool_call pendant le stream
  2. Lance asyncio.create_task() vers Runware (non-bloquant)
  3. Injecte automatiquement les LoRA + trigger words des acteurs
  présents
  4. Renvoie un résultat synthétique à Grok qui continue la narration
  5. Quand l'image est prête → push SSE image_ready vers le frontend

  ---
  Protocole SSE (backend → frontend)

  ┌───────────────────┬────────────────┬─────────────────────────┐
  │       Event       │     Quand      │         Données         │
  ├───────────────────┼────────────────┼─────────────────────────┤
  │ narration_delta   │ Texte streamé  │ {content: "Tu           │
  │                   │                │ prends..."}             │
  ├───────────────────┼────────────────┼─────────────────────────┤
  │ image_requested   │ Tool call      │ {index, prompt, actors} │
  │                   │ détecté        │                         │
  ├───────────────────┼────────────────┼─────────────────────────┤
  │ image_ready       │ Runware        │ {index, url, cost,      │
  │                   │ terminé        │ seed}                   │
  ├───────────────────┼────────────────┼─────────────────────────┤
  │ choices_available │ Fin de         │ {choices: [{id, text}]} │
  │                   │ séquence       │                         │
  ├───────────────────┼────────────────┼─────────────────────────┤
  │ sequence_complete │ Tout fini      │ {costs: {grok, images,  │
  │                   │                │ total}}                 │
  └───────────────────┴────────────────┴─────────────────────────┘

  ---
  Cohérence visuelle

  Un ConsistencyTracker côté backend suit :
  - Location actuelle (identique si inchangée)
  - Vêtements de chaque acteur (persistent sauf changement explicite)
  - Props/ambiance (bougies, pluie, etc.)

  Cet état est injecté dans le system prompt de Grok à chaque
  séquence + validé via les champs clothing_state et
  location_description du function call.

  ---
  Modèle Grok

  grok-4-1-fast-non-reasoning : $0.20/$0.50 par 1M tokens (10x moins
  cher que le 4.20), contexte 2M, supporte function calling +
  streaming. Idéal pour l'orchestration rapide.

  ---
  Features debug

  - System prompt éditable en live + bouton "Ask Grok to modify"
  - Log détaillé des coûts par séquence (tokens in/out, coût image×5,
   total)
  - Prompts générés visibles pour chaque image
  - Phase 1 reste accessible en tant qu'onglet séparé pour tester les
   modèles