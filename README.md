# Odoo 18 — Configuration Claude

Configuration template pour un projet Odoo 18 avec Claude Code.

## Contenu

### Fichiers racine

| Fichier | Description |
|---------|-------------|
| **CLAUDE.md** | Instructions projet pour Claude (conventions, workflow, skills) |
| **SERVICE.md** | Guide de gestion du service Odoo (16 commandes) |
| **MCP.md** | Documentation du serveur MCP (20 outils d'introspection) |
| **odoo-service.sh** | Script de gestion du service |
| **odoo.conf** | Configuration Odoo |
| **mcp_bridge_cli.py** | CLI pour interagir avec le serveur MCP |
| **odoo_mcp_bridge.py** | Bridge stdio pour clients MCP externes |
| **init.sh** | Script interactif d'initialisation |

### Structure `.claude/`

```
.claude/
  settings.json              # Permissions equipe (partage, versionne)
  settings.local.json        # Permissions personnelles (gitignore)
  agents/                    # 8 agents specialises
    odoo-code-review.md        Revue de code Odoo (sonnet)
    odoo-code-tracer.md        Trace d'execution (sonnet)
    odoo-inspector.md          Exploration de l'instance (sonnet)
    meta-debugger.md           Boucle debug automatisee (sonnet)
    context-manager.md         Gestion memoire de session (haiku)
    hindsight-notes.md         Registre erreurs/tips (haiku)
    planner.md                 Planification features (opus)
    odoo-fn-advisor.md         Conseiller fonctionnel (sonnet)
  rules/                     # 15 regles auto-activees par glob
    coding-style.md            Style de code (global)
    odoo-models.md             ORM et modeles
    odoo-views.md              Vues XML
    odoo-actions.md            Actions et menus
    odoo-data.md               Fichiers de donnees
    odoo-controller.md         Controleurs HTTP
    odoo-owl.md                Composants OWL/JS
    odoo-reporting.md          Rapports QWeb
    odoo-web.md                Website et SCSS
    odoo-pos.md                Point de Vente
    odoo-cli.md                CLI et deploiement
    odoo-migration.md          Migration cross-version
    odoo-no-core-modification.md  Interdiction modifier le core
    security.md                Securite ACL et rules
    testing.md                 Tests Python/JS
  skills/                    # 34 skills (22 dev + 11 fonctionnels + 1 MCP)
    odoo-dev-*/                22 guides dev Odoo 18
    odoo-fn-*/                 11 domaines fonctionnels (860 fichiers, 8.6 MB)
    mcp/                       Interrogation instance Odoo live
  data/                      # Donnees persistantes
    errors-registry.csv        Registre d'erreurs connues
    tips-and-tricks.csv        Tips et bonnes pratiques
  memory/                    # Memoire de session (gitignore)
```

### Module MCP

```
addons_dev/mcp_service/      # Module Odoo MCP (20 outils, 51 tests)
```

## Installation

```bash
./init.sh
```

Le script interactif demande :
1. Chemin racine du projet Odoo
2. Port HTTP (defaut: 8069)
3. Nom de la base de donnees
4. Filtre de bases de donnees

Puis remplace les 4 placeholders (`__PROJECT_ROOT__`, `__PORT__`, `__DB_NAME__`, `__DB_FILTER__`) dans 19 fichiers de configuration.

## Utilisation

Apres `init.sh`, copier le tout dans votre projet Odoo :

```bash
cp -r ./* /chemin/vers/projet/
cp -r .claude /chemin/vers/projet/
```

Puis demarrer le service :

```bash
./odoo-service.sh start
./odoo-service.sh status
```

## Normes Claude Code

Cette configuration respecte les conventions officielles Claude Code :

- **CLAUDE.md** : < 500 lignes, imports `@file`, conventions ALWAYS/NEVER
- **Agents** : frontmatter YAML (name, description, model, tools)
- **Skills** : SKILL.md par repertoire, `user-invocable` pour les slash commands
- **Rules** : frontmatter `paths` avec glob patterns, auto-activation
- **Settings** : `settings.json` (equipe) + `settings.local.json` (personnel, gitignore)
- **Nommage** : kebab-case partout (agents, skills, rules)
