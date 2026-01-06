# Mémoire de Session - BoondManager CSV Importer

## Vue d'ensemble
Application FastAPI pour importer des entités dans BoondManager via CSV avec interface web.

---

## Modules développés

### 1. **Deliveries** (Prestations)
- Import de prestations avec création automatique de :
  - Purchase (pour consultants externes)
  - Order avec upload de documents
- **Mise à jour automatique des contrats** :
  - Grouper les deliveries par `project_id`
  - Trouver la dernière delivery (par `end_date`)
  - Si `end_date < 31/12/2025` → mettre à jour le contrat de la ressource
  - PUT `/contracts/{id}` avec `endDate` + `endReason: 4`
  - Contrat ciblé = celui avec `startDate` la plus récente

### 2. **Resources** (Ressources)
- Mise à jour du type et société fournisseur des ressources
- PUT `/resources/{id}/information` pour `typeOf`
- GET `/companies/{id}/contacts` pour récupérer le premier contact
- PUT `/resources/{id}/administrative` pour `providerCompany` et `providerContact`

### 3. **Resource Contracts** (Contrats des ressources)
- Création de contrats via CSV
- `typeOf=0` → utilise `contract_monthly_salary` (`monthlySalary`)
- `typeOf!=0` → utilise `contract_daily_production_cost` (`contractAverageDailyProductionCost`)
- `contract_renewal=VRAI` → lie au contrat précédent via `parentContract`
- `workingTimeType: 0` par défaut
- `contract_end_date` optionnel
- **Bouton "Supprimer les contrats"** :
  - GET `/resources/{id}/administrative` → récupérer IDs des contrats
  - DELETE `/contracts/{id}` pour chaque contrat
  - Dialog de confirmation avec comptage

### 4. **Projects** (Projets)
- Import standard via router commun

---

## Méthodes ajoutées dans `boond_client.py`

| Méthode | Endpoint | Description |
|---------|----------|-------------|
| `get_resource_contracts` | GET /resources/{id}/administrative | Récupère les IDs des contrats |
| `get_resource_contracts_with_details` | GET /contracts/{id} (multiple) | Récupère contrats avec startDate/endDate |
| `delete_contract` | DELETE /contracts/{id} | Supprime un contrat |
| `update_contract` | PUT /contracts/{id} | Met à jour endDate + endReason |
| `create_resource_contract` | POST /contracts | Crée un contrat pour une ressource |
| `get_contract` | GET /contracts/{id} | Récupère les détails d'un contrat |
| `get_project` | GET /projects/{id} | Récupère les détails d'un projet |
| `get_resource_positionings` | GET /resources/{id}/positionings | Récupère les positionnements |
| `update_positioning` | PUT /positionings/{id} | Met à jour mainManager |

---

## Fixes appliqués

1. **Case sensitivity colonne Contrat** : Cherche `contrat` ET `Contrat`
2. **Newlines littéraux** : Conversion `\\n` → `\n` dans les commentaires
3. **Onglet Resources vide** : Ajout null check dans `initializeEntityTab`
4. **Attributs API contrats** : `monthlySalary` et `contractAverageDailyProductionCost`
5. **Condition date contrat** : Retiré `end_date > today` (données historiques)

---

## Interface utilisateur

- **Onglets** : Projects, Deliveries, Resources, Resource Contracts
- **Onglet Contracts retiré** (fusionné dans Resource Contracts)
- **Bouton "Supprimer les contrats"** dans Resource Contracts (rouge)
- **Barre de progression** avec log d'actions en temps réel (SSE)
- **CSS** : `.btn-danger`, `.progress-header`, `.action-log`

---

## Fonctionnalité "Update Positionings" (désactivée)

Développée puis retirée car `updateDate` est en lecture seule.
- Objectif initial : mettre à jour la date du positionnement
- Changé vers `mainManager=1099` mais finalement bouton retiré
- Le code backend reste dans `deliveries.py` (endpoint `/update-positionings`)

---

## Structure des fichiers modifiés

```
app/
├── boond_client.py          # Client API avec toutes les méthodes
├── routers/
│   ├── deliveries.py        # Router custom avec logique contrat
│   ├── resources.py         # Router custom pour type/provider
│   └── resource_contracts.py # Router avec delete endpoint
├── static/
│   ├── index.html           # Template avec boutons
│   ├── app.js               # Frontend JS avec SSE
│   └── style.css            # Styles btn-danger, progress
```

---

## Commits récents

1. `7d6e5f8` - Remove update positionings button and related code
2. `7779cd3` - Change update positionings to set mainManager=1099
3. `ca04d19` - Update positionings: use updateDate + progress bar
4. `b89339f` - Add update positionings button for deliveries
5. `a334dc4` - Remove 'end_date > today' condition for contract update
6. `e4373cd` - Add delete contracts functionality for Resource Contracts
