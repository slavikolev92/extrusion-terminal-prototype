# Material Identification Research Report

**Prepared:** 2026-08-15

**Repository:** ERP Research

**Purpose:** Consolidate everything the repository currently says about raw materials, purchased materials, production outputs, material characteristics, material identity, inventory differentiation, and possible material-number approaches so it can inform the new MES/MRP project.

## Executive Summary

The repository does **not** contain an approved business-facing material identification number, internal SKU, `item_code`, `material_number`, stock code, barcode, or equivalent numbering scheme.

The clearest existing decision is the opposite: for PE polymers and purchased PP films, the display name is the human identifier and the auto-increment database primary key is the technical identifier. `milestone-1.md` generalizes this as “No internal SKU for any material type.” This was recorded in the M1 plan's historical decision table, not as a numbered decision in `decision-log.md`. Sources: `domain-knowledge/master-data.md` § Category 1: PE Polymers (Extruded In-House) > Naming Convention; § Category 1b: PP Films (Purchased Semi-Finished) > Naming Convention; `docs/plans/milestone-1.md` § Decisions Made; `docs/decision-log.md` § Decisions.

However, the project **has** done substantial work on material identity in a different sense:

- It defines the tracked raw and purchased material families and many of their characteristics.
- It defines exact semantic identity keys for in-house outputs: 9 attributes for `film_roll`, 14 for `bag`, and 7 for `sheet`.
- It defines how matching output from different production orders pools into the same inventory Item.
- It separates Item identity from lot/batch references, production receipt records, stock transactions, customer/order context, and future individual-roll identity.
- It defines which facts must **not** create another material: receipt cost, source PO/OC, customer, intended WIP/finished use, tare, quantity, and—in a deliberate rule—supplier-grade substitutions within the same normalized recipe type.

The current model can therefore answer much of **“are these two outputs the same inventory material?”** It cannot yet answer **“what stable number should a worker, label, integration, or external MES/MRP use for that material?”**

The most important findings for the new project are:

1. A material-master number, a supplier lot, a production batch/receipt, and an individual physical roll are different grains and cannot safely share one identifier.
2. Raw-material naming conventions exist, but formal raw-material uniqueness keys do not.
3. Produced-material uniqueness is much more developed than raw-material uniqueness, but the database constraint, concurrency, canonical-null, and fingerprint implementation details remain open.
4. Waste/scrap, purchased components, purchased recycled LDPE naming, and individual-roll/container identity are incomplete or deferred.
5. Two discarded/non-authoritative alternatives contain human-facing codes: a stale early database example used `FG-ABC-001`, and a transient ERPNext experiment suggests `KAM-FILM-001`. Neither is an approved ERP Research decision. Both are customer-specific directions and therefore conflict with the custom ERP's current rule that customer is excluded from Item identity.

This report intentionally does not choose a new number format. It preserves the verified source material, identifies gaps, and states the constraints that a later numbering decision must address.

## Source Status and Research Method

### Evidence status used in this report

- **Established:** current domain documents and accepted architecture decisions.
- **Planned/current context:** milestone plans and decision-log entries. These are useful, but a plan can contain older wording that has been superseded by a later domain rule or decision.
- **Open/provisional:** `open-issues.md` and active working files. These identify real gaps but are not final designs.
- **Historical/superseded:** `archive/`. These files show how the design evolved; current canonical documents control when they disagree.
- **Transient/non-authoritative:** `tmp/`, including interviews, prototypes, onboarding derivatives, and the ERPNext test handoff. These can preserve useful evidence or alternatives but do not establish the custom ERP design.

### Coverage

Before this report was added, the reviewed source corpus contained 373 documentation-like artifacts:

| Format | Count |
|---|---:|
| Markdown | 354 |
| HTML | 3 |
| JSON | 8 |
| Mermaid | 8 |
| **Total** | **373** |

The research process was:

1. Read the current authoritative Markdown corpus under `domain-knowledge/` and `architecture/` in full.
2. Read the current plans, decision log, open-issue register, active working files, and relevant policies under `docs/` and `reviews-and-questions/` in full.
3. Scan all root, `archive/`, `tmp/`, and `prompts/` documentation for a controlled material vocabulary, including material families, inputs/outputs, recipes, identity, SKU/code, lots/batches, rolls, labels, and inventory. Substantive historical and transient hits were then read and reconciled against current sources.
4. Scan the non-Markdown HTML, JSON, and Mermaid artifacts for the same material concepts.
5. Run a repository-wide exact search for terms such as internal SKU, material code, item code, stock code, supplier SKU, part number, serial number, barcode, and QR code.

No external sources were used; this is a repository-evidence report. An absence claim means no approved scheme was located anywhere in the reviewed repository corpus. It does not prove that a number never existed in an external spreadsheet, supplier system, label, or undocumented factory practice.

## 1. The Material Landscape Defined by the Repository

### 1.1 Current Item/material families

| Family | Exact documented variants | Role | Current status |
|---|---|---|---|
| PE polymers | `LDPE`, `LLDPE`, `mLLDPE`, `HDPE`, `EVA`, `Recycled LDPE` | Raw pellets/granules consumed by Extrusion | Tracked, but the allowed-value lists are not fully aligned; HDPE is rare and EVA is planned rather than currently used |
| Purchased PP films | `BOPP`, `CPP` | Purchased pre-extruded semi-finished rolls; enter at R&S, Printing, or Confection rather than Extrusion | Tracked |
| Additives | Filler (`CaCO₃`), Color masterbatch, Antistatic, Anti-slip, UV protection | Functional Extrusion recipe inputs | Tracked |
| Inks | Color plus formulation, such as `Red`, `Red 485B`, `Red 032C` | Printing consumables | Tracked as Items whether purchased or mixed on site |
| Solvents | Ethyl Acetate, Methoxypropanol, and legacy generic “solvent” | Printing thinning/cleaning consumables | Tracked; generic classification remains poor |
| Purchased components | Cores, pallets/packaging, stretch wrap, labels | Packaging/tare-related inputs | Tracking is TBD |
| In-house output | `film_roll`, `bag`, `sheet` | Intermediate or final production output, classified by physical form | Tracked; automatically found/created |
| Waste/scrap | Exact type(s) and identity key undecided | Non-output material captured at OC end-of-run, potentially later classified as waste, scrap for sale, recyclable, or rework | Open under OI-015 |
| In-house inline regrind | Clean material returned immediately into the same extrusion run | Closed-loop process material | Deliberately invisible to inventory |

Sources: `domain-knowledge/master-data.md` § Item Categories Overview; § Key Distinction: Extruded vs. Purchased Films; §§ Category 1 through Category 6; `reviews-and-questions/open-issues.md` § OI-015: Waste/Scrap Item Type and Identity Key; `reviews-and-questions/oi-015-waste-model-working.md` § Current Repo State; § Main Design Questions OI-015 Must Answer.

### 1.2 Inputs, intermediates, and final output are not separate Item classes

The custom ERP deliberately classifies in-house output by **physical form**, not by lifecycle stage:

- `film_roll`: continuous film on a roll/web from Extrusion, R&S, or Printing. A flat film web on a roll still belongs here.
- `bag`: Confection output whose `confection_product_form` is `bag` or `sack`.
- `sheet`: discrete cut-to-length Confection output whose `confection_product_form` is `sheet`.

“Raw,” “semi-finished,” “WIP,” “final,” “make-to-stock,” and “customer product” describe context or intended use; they do not create separate Item types. A physically identical roll can be an intermediate in one route and dispatchable output in another. If its semantic identity key matches, it pools into the same Item.

Sources: `domain-knowledge/master-data.md` § Category 6: Film Products (Production Output) > Purpose; `reviews-and-questions/open-issues.md` § OI-016: WIP/FG Financial Categorization — RESOLVED; `architecture/decisions/004-internal-production-orders-mts-mto-separation.md` § Key Design Elements > `find_or_create_item`.

### 1.3 The commercial product taxonomy is separate

The PO/CO design also has a ten-value commercial `product_category` taxonomy:

- `ТС Фолио`
- `СПП Плик`
- `ПЕ Торба`
- `БОПП Плик`
- `БОПП Фолио`
- `ПЕ Фолио`
- `ПЕ Ръкав`
- `ПЕ Плик`
- `ТС Ръкав`
- `HDPE Плик`

These values describe the ordered/commercial product. They are not Item types and are not included in any produced-material identity key. The category list also contains no waste/scrap value, which OI-015 explicitly flags.

The distinction was based on actual spreadsheet analysis rather than terminology alone. The legacy “Type of Product” field mixed category, dimensions, gussets, flap, print project, ventilation, handles, and sometimes additive percentages into free text. Analysis of 19,202 historical orders found that thermal-shrink film/sleeve represented about 41% and could not be inferred reliably from operation slots or film form. The chosen result was a manual commercial category plus a display string composed from structured specifications. This history reinforces that commercial category and technical Item identity solve different problems.

Sources: `domain-knowledge/po-oc-field-definitions.md` § Production Order (PO) Fields > 6. Type of Product; `domain-knowledge/customer-orders.md` § 6. `product_category` Governance; `reviews-and-questions/open-issues.md` § OI-015: Waste/Scrap Item Type and Identity Key; raw decision evidence: `tmp/interview/interview-22-02-2026.md` § Q5. Commercial Category Derivation Rules for Type of Product; `tmp/excel-to-erp-field-mapping.md` § Type of Product.

## 2. What “Unique Identification” Currently Means

The repository contains several identifiers and identity mechanisms. They are related, but they have different grains.

| Concept | Grain | Current mechanism | Can it serve as the requested material number today? |
|---|---|---|---|
| Database Item identifier | One pooled Item master row | Auto-increment database PK | Technical identifier only; not defined as a portable, human-facing material number |
| Display name | One Item master row, human-facing | Category-specific descriptive name | Current human identifier, but not always a complete or formally unique key |
| Business material number/SKU | One Item master row | **Not defined** | No |
| Semantic identity key | Material specification used for pooling | Explicit 9/14/7-attribute keys for produced output; no equivalent formal keys for raw types | Strong basis for deciding “same material,” but not itself a concise number |
| Supplier product/grade code | Supplier's product definition | Polymer/PP grade or product-code token; additive brand/code in name | External/natural descriptor, not an ERP-generated universal identifier |
| `recipe_fingerprint` | Canonicalized Extrusion recipe contribution to output identity | Hash/payload design partly unresolved | Identity component, not a human material number |
| Supplier lot/batch | A received/used batch | Free-text reference on OC blend lines only | No; not a stock dimension or Item identity |
| Production receipt line | One grouped output receipt event | `OCReceiptLine` PK plus Item/OC links | Source-event identifier, not material-master identity |
| Stock transaction | One inventory ledger event | `StockTransaction` PK and source links | Ledger/audit identity, not material identity |
| Individual physical roll/container | One stock unit | Not present in current inventory; future `OutputRoll`/`OutputContainer` concepts | Deferred |
| CO/PO/OC numbers | Commercial demand and work records | `CO-0001`; sequential PO; PO + operation suffix | Explicitly not material numbers |
| Machine code | Equipment master | Stable machine code/name | Equipment identifier only |

This distinction is the single most important prerequisite for the new project's numbering work. A material-master number can identify a reusable specification. It cannot, without changing grain, also identify every supplier delivery, production receipt, or individual physical roll.

Sources: `domain-knowledge/master-data.md` § Category 1: PE Polymers (Extruded In-House) > Naming Convention; § Category 6: Film Products (Production Output); `architecture/decisions/003-item-level-inventory-with-wac.md` § Decision; `domain-knowledge/po-oc-field-definitions.md` § Inventory Item Output (All OC Types, All PO Types); `domain-knowledge/production-orders.md` § Numbering Convention; `docs/plans/milestone-3.md` § Open Questions.

## 3. Raw and Purchased Materials

### 3.1 PE polymers

#### Current and to-be identification

The as-is problem was inconsistent naming: operators might see only a brand such as “Sabic” or an ambiguous descriptor such as “hard” or “soft.” The to-be naming convention is:

`[Manufacturer] [Material Type] [Grade]`

Canonical examples:

- `SABIC LDPE 2100TN21`
- `SHELL LLDPE 18F1B`
- `PETILEN PE 0321T`

The documents state explicitly that there is no internal SKU. The display name is the human identifier, and the database primary key is the technical identifier.

Sources: `domain-knowledge/master-data.md` § Category 1: PE Polymers (Extruded In-House) > Current Identification; > Naming Convention.

#### Defined characteristics

| Fact | Role |
|---|---|
| `name` | Descriptive human identifier |
| `polymer_type` | Functional type: currently documented as LDPE, LLDPE, mLLDPE, Recycled LDPE in the field table |
| `grade` | Manufacturer/producer-specific grade or product code |
| `manufacturer` | Polymer producer |
| `melt_flow_index` | Optional technical property, g/10 min |
| `density` | Optional technical property, g/cm³ |
| `melt_temperature` | Optional technical property, °C |

The same table also lists `quantity_kg`, `total_cost`, `receipt_date`, and receipt-entry `cost_per_kg`. These are delivery/receipt facts, not stable material-master identity. The document now states explicitly that `cost_per_kg` is not a stored Item cost field.

Source: `domain-knowledge/master-data.md` § Category 1: PE Polymers (Extruded In-House) > Attributes for PE Polymers.

#### Known gaps

- No formal composite uniqueness rule says that `manufacturer + polymer_type + grade` must be unique.
- No normalization rules exist for manufacturer or grade capitalization, punctuation, aliases, or supplier spelling.
- HDPE and EVA appear in the “Polymer Types Used” table, but the PE Item field list and produced-output `material_type` identity list omit them. `HDPE Плик` nevertheless appears in the commercial product categories.
- The plan says technical data still needs to be compiled from supplier technical sheets/certificates.
- The term `grade` has a different meaning for production output, where it means `Prime` or `B-Grade`.

Sources: `domain-knowledge/master-data.md` § Category 1: PE Polymers (Extruded In-House); § Category 6: Film Products (Production Output); `docs/plans/milestone-1.md` § Remaining Pre-Implementation Work; `domain-knowledge/po-oc-field-definitions.md` § Production Order (PO) Fields > 6. Type of Product.

### 3.2 Recycled LDPE

Two sources were identified:

1. Purchased recycled LDPE from an external recycler. This should be an inventory Item with normal receipt and cost treatment.
2. In-house regrind produced and immediately consumed in the same Extrusion run. This is deliberately not separately receipted or consumed because it never leaves the closed loop.

The purchased material's naming convention is explicitly deferred because the project did not know what manufacturer/grade information would be available on supplier invoices. It was expected to follow the polymer naming pattern loosely once real invoice data was examined.

There is also a documentation tension: the recycled-LDPE paragraph says purchased material has “lot info,” while ADR-003 and the PE attribute table say a lot is not an Item or receipt inventory dimension and is only an OC reference. The ADR is the stronger current architecture decision.

Sources: `domain-knowledge/master-data.md` § Category 1: PE Polymers (Extruded In-House) > Recycled LDPE; `architecture/decisions/003-item-level-inventory-with-wac.md` § Decision > Lot/Batch on Operation Cards; `docs/plans/deferred-functionality.md` § Scrap Recycling via Internal PO.

### 3.3 Purchased PP films

BOPP and CPP are purchased pre-extruded semi-finished rolls. They do not pass through in-house Extrusion. They can begin at R&S, Printing, or Confection and can later become `film_roll`, `bag`, or `sheet` output.

The display-name format is:

`[Material Type] [Product Code] [Width]`

Canonical examples:

- `BOPP PLCBZ25 960mm`
- `CPP XK318 1200mm`

The producer is tracked but deliberately omitted from the display name. As with PE polymers, the documents explicitly say there is no internal SKU.

Sources: `domain-knowledge/master-data.md` § Category 1b: PP Films (Purchased Semi-Finished) > Description; > Naming Convention.

#### Defined characteristics

| Fact | Role |
|---|---|
| `name` | `[Type] [Product Code] [Width]` human identifier |
| `film_type` | BOPP or CPP |
| `producer` | Company that made/extruded the film, not a reseller |
| `grade` | Producer-specific product code |
| `width` | Purchased roll width |
| `thickness` | Film thickness |
| `treatment_type` | Existing surface treatment |
| `film_form` | Required physical form: Tubular, Semi-tubular, or Flat sheet |
| `cost_per_kg` | Receipt-entry valuation input, not stable identity |

PP film is tracked in kg and is gross-only; it has no secondary net quantity. Producers do not provide lot/batch numbers, so the design has no PP lot field on either the Item or OC.

Sources: `domain-knowledge/master-data.md` § Category 1b: PP Films (Purchased Semi-Finished) > Attributes for PP Films; `architecture/decisions/005-inventory-weight-basis-gross-canonical.md` § Key Design Elements > Scope; `docs/decision-log.md` § Decisions (DL-003).

#### Known gaps

- The display name uses type, product code, and width, while the required attributes also include producer, thickness, treatment, and film form. The docs do not say whether two records with the same display name but different values for those other characteristics are allowed or how a worker distinguishes them.
- The raw PP field names (`film_type`, `width`, `thickness`, `treatment_type`) do not exactly match downstream `film_roll` identity fields (`material_type`, `width_mm`, `thickness_mm`, `treatment`). The transformation/mapping is conceptually clear but not specified as a formal mapping contract.
- Units are not embedded in the PP master field names even though downstream output uses explicit `_mm` names.

Sources: `domain-knowledge/master-data.md` § Category 1b: PP Films (Purchased Semi-Finished); § Category 6: Film Products (Production Output) > Attributes for Film Products (film_roll).

### 3.4 Additives

Functional categories currently identified are:

- Filler (`CaCO₃`)
- Color masterbatch
- Antistatic
- Anti-slip
- UV protection

Additives can be masterbatches—carrier polymer plus concentrated additive—or pure additives. “Polybatch” and “Masterbatch” are brands/forms, not functional categories.

The canonical document uses the phrase “many distinct additive SKUs,” with examples such as `Polybatch VOA 66` and `Blue AGL 4535`. In context, these are supplier/brand product identities represented by the full product `name`; no separate internal SKU field or internal-number scheme is defined.

Defined fields are `name`, `additive_type`, `supplier`, receipt-entry `cost_per_kg`, and optional `color`, `form`, and `lot_batch_number`.

Important identity rule: the operational Extrusion recipe selects a specific additive Item, but the finished-output `recipe_fingerprint` uses the normalized `additive_type`, not the supplier Item FK. Substitution between additive Items of the same functional type is therefore intended to produce the same output identity.

Sources: `domain-knowledge/master-data.md` § Category 2: Additives; `domain-knowledge/production-orders.md` § Recipe Business Rules.

The optional additive `lot_batch_number` field conflicts with ADR-003's stronger rule that lot/batch is OC text only and not an inventory attribute. This should be treated as stale or unresolved wording, not as an established lot-level stock model.

### 3.5 Inks

Inks are identified by color and formulation. A base color can have multiple formulations, such as `Red`, `Red 485B`, and `Red 032C`.

Whether ink is purchased pre-mixed or mixed on site does not change its Item treatment. Defined fields are:

- `name`: color plus formulation
- `color`: base color category
- optional `supplier`
- receipt-entry `cost_per_kg`

Printing can reference up to eight specific ink Items through `ink_station_N_item` FKs. The paired anilox specification is process text, not material identity. The current system scope does not create per-job ink consumption from a recipe; period-level allocation is used until weigh-in/weigh-out capture is introduced.

Sources: `domain-knowledge/master-data.md` § Category 3: Inks; `domain-knowledge/po-oc-field-definitions.md` § Printing Order Card (OC) Fields > 3. Inks / Solvents Configuration → Ink Stations; `docs/plans/deferred-functionality.md` § Per-OC Ink/Solvent Consumption Tracking.

There is no formal ink uniqueness rule, no internal number, and no structured formulation entity. Free-text/color naming could therefore duplicate or fragment equivalent inks.

### 3.6 Solvents

The repo records a known as-is classification problem: some solvent is recorded only as generic “solvent,” while other records name Ethyl Acetate or Methoxypropanol. The to-be direction is to require a specific solvent type.

Defined fields are `name`, `solvent_type`, `supplier`, and receipt-entry `cost_per_kg`. There is no internal number or formal uniqueness key.

Sources: `domain-knowledge/master-data.md` § Category 4: Solvents.

### 3.7 Purchased components and packaging

Cores and packaging materials are named as a material family, but Item tracking remains TBD. The UOM table says cores would use pieces while all other current material/output categories use kg.

The system already needs core/container facts to calculate gross and net output, but those facts are currently receipt-line tare data rather than inventory consumption of a core or package Item. Pallets, stretch wrap, and labels are operationally referenced, yet no master-data identity, number, stock, or consumption design exists for them.

Sources: `domain-knowledge/master-data.md` § Category 5: Purchased Components; § Unit of Measure Conventions; `domain-knowledge/operational-procedures.md` § Dispatch — Film Rolls; § Dispatch — Bags/Sheets; `domain-knowledge/po-oc-field-definitions.md` § Inventory Item Output (All OC Types, All PO Types).

### 3.8 Shared units and calculation references

All current raw/purchased materials and in-house film products are inventoried in kg; only cores use pieces. Width and thickness are material characteristics, while meters and finished-unit counts are secondary production targets rather than stock UOMs.

The target-meter calculation records system density references of LDPE 0.92, LLDPE 0.92, HDPE 0.95, BOPP 0.90, and CPP 0.91 g/cm³. PE orders use a weighted average of blend-component densities; PP uses the purchased input type. These densities support planning/calculation and are not defined as material-number components. The current list does not state the density treatment for mLLDPE or Recycled LDPE.

Sources: `domain-knowledge/master-data.md` § Unit of Measure Conventions; `domain-knowledge/production-orders.md` § Target Quantity.

## 4. In-House Production Output Identity

### 4.1 Automatic creation and pooling

At end-of-run, every Completed OC with positive good output calls `find_or_create_item`. The shift manager does not manually create a new production-output Item. The service builds the applicable per-type semantic key, finds an existing match, or creates a new Item. Corrected receipt-line entry after a clean reversal uses the same identity lookup without rerunning the OC lifecycle.

If output from two different POs has the same identity key, it pools into the same Item quantity and WAC. Customer, source PO, source OC, MTS/MTO purpose, and whether the stock is “intermediate” or “final” do not split the Item.

Sources: `domain-knowledge/master-data.md` § Category 6: Film Products (Production Output) > How Items Are Created; `domain-knowledge/inventory-management.md` § Production Output to Inventory > Production Output Item Creation (`find_or_create_item`); `architecture/decisions/004-internal-production-orders-mts-mto-separation.md` § Key Design Elements > `find_or_create_item`.

### 4.2 `film_roll` identity: 9 attributes

| Identity attribute | Meaning/source |
|---|---|
| `material_type` | Dominant/highest-percentage PE polymer across the Extrusion recipe, or BOPP/CPP inherited from purchased PP input |
| `width_mm` | Lay-flat width; set by Extrusion or R&S, with receipt-line override when needed |
| `thickness_mm` | Set by Extrusion; inherited downstream |
| `film_form` | Tubular, Semi-tubular, or Flat sheet |
| `side_gusset_depth_mm` | Nullable; null means no side gusset |
| `treatment` | None, One-sided, or Two-sided corona treatment |
| `grade` | Prime or B-Grade, applied per receipt line |
| `print_project` | Nullable free-text print design; null means unprinted |
| `recipe_fingerprint` | Nullable canonical Extrusion-recipe identity; null means no in-house Extrusion in the chain |

The descriptive `name` and free-text `notes` are not listed as key attributes. An example auto-generated name is `LDPE 400mm 50μm extruded`, but the exact deterministic name grammar and collision policy remain unspecified.

Source: `domain-knowledge/master-data.md` § Category 6: Film Products (Production Output) > Attributes for Film Products (film_roll).

### 4.3 `bag` identity: 14 attributes

| Identity attribute | Meaning/source |
|---|---|
| `material_type` | Inherited normalized material type |
| `width_mm` | Final Confection output width |
| `length_mm` | Final cut/bag length |
| `thickness_mm` | Inherited film thickness |
| `confection_product_form` | `bag` or `sack` |
| `bottom_gusset_depth_mm` | Nullable bottom-gusset depth |
| `flap_depth_mm` | Nullable flap depth |
| `handles` | Whether handles are present |
| `ventilation_count` | Number of ventilation openings; null/zero means none |
| `ventilation_diameter_mm` | Ventilation-hole diameter; current configured values are 6mm and 16mm |
| `side_gusset_depth_mm` | Inherited side-gusset depth |
| `grade` | Prime or B-Grade |
| `print_project` | Nullable inherited print design |
| `recipe_fingerprint` | Nullable inherited Extrusion recipe identity |

Explicitly excluded from bag identity are `treatment`, `folding`, and `film_form`. Folding is an operational Confection setting, not a material-master characteristic.

Sources: `domain-knowledge/master-data.md` § Category 6: Film Products (Production Output) > Attributes for Film Products (bag); `domain-knowledge/po-oc-field-definitions.md` § Confection Order Card (OC) Fields.

### 4.4 `sheet` identity: 7 attributes

| Identity attribute | Meaning/source |
|---|---|
| `material_type` | Inherited normalized material type |
| `width_mm` | Final sheet width |
| `length_mm` | Final sheet length |
| `thickness_mm` | Inherited film thickness |
| `grade` | Prime or B-Grade |
| `print_project` | Nullable inherited print design |
| `recipe_fingerprint` | Nullable inherited Extrusion recipe identity |

Bag-specific features, `treatment`, `film_form`, and `side_gusset_depth_mm` are explicitly excluded.

Source: `domain-knowledge/master-data.md` § Category 6: Film Products (Production Output) > Attributes for Film Products (sheet).

### 4.5 Output-specification and inheritance rules

The system does not infer finished dimensions through a general physics/transformation engine.

- Extrusion creates its key from explicit OC/PO specifications plus system-derived `material_type` and `recipe_fingerprint`.
- A non-Extrusion OC starts from the selected input Item's accumulated attributes.
- R&S, Printing, or Confection applies only the structured fields that operation explicitly changes.
- Receipt-line `grade` and applicable `width_mm` overrides are applied last.

A current discussion-complete but not yet propagated D-1 decision says downstream `material_input` and `input_quantity_kg` should require explicit selection/confirmation, with upstream output merely pre-filtering candidates. Some current M1 prose still says the system auto-fills the input when unambiguous. That workflow inconsistency affects material selection, but it does not change the defined output identity keys.

Sources: `domain-knowledge/production-orders.md` § What Data Lives Where; `domain-knowledge/master-data.md` § Category 6: Film Products (Production Output) > How Items Are Created; `reviews-and-questions/lifecycle-d1-material-input-auto-fill.md` § Resolved Decision; § Propagation Notes.

### 4.6 Normalization already defined

Several anti-duplication rules exist:

- Width and thickness must use fixed decimal precision for matching.
- `print_project` is stripped of surrounding whitespace and compared case-insensitively with `iexact`.
- Null `print_project` means the valid identity state “unprinted/no design.”
- Each Extrusion layer's blend percentages sum to 100.
- Multi-layer thickness ratios are whole-integer percentages summing to 100; nominal equal three-layer film is represented as `34 / 33 / 33`.
- Recipe contributions are ordered/canonicalized sufficiently in concept to produce a stable fingerprint, although the final serialization/hash contract is still open.

Source: `domain-knowledge/inventory-management.md` § Production Output to Inventory > Production Output Item Creation (`find_or_create_item`); `domain-knowledge/po-oc-field-definitions.md` § Multi-Layer Extrusion; § Blend Recipe Rules.

### 4.7 Important exclusions from output identity

The following facts deliberately do not create a different material Item:

- Customer
- Customer Order, Production Order, or Operation Card number
- MTO versus MTS purpose
- Intended WIP/intermediate/final use
- Production stage such as E, R1, P, R2, or C
- Receipt cost or WAC
- Receipt quantity
- Roll/container count and tare weight
- Source supplier-grade Item when the recipe substitution remains within the same normalized `polymer_type` or `additive_type`
- Color as a separately stored output key; color is intended to be derived from recipe data

The last rule is especially important: two runs can consume different supplier/grade Items but deliberately become the same output Item if their functional polymer/additive types and percentages match.

Sources: `domain-knowledge/master-data.md` § Category 6: Film Products (Production Output); `domain-knowledge/production-orders.md` § Recipe Business Rules; `archive/26-F1-identity-key-redesign.md` § Recipe Fingerprint Specification; § Attributes Removed.

## 5. Recipe, BOM, and Material-Selection Information

### 5.1 No standalone recipe/BOM master in the custom ERP scope

The current custom ERP design stores recipe and production parameters on OCs/POs. Repeating work is handled by copying a prior PO. A separate Recipe/BOM entity was deliberately deferred because duplication was considered sufficient for the first implementation.

Sources: `domain-knowledge/production-orders.md` § Order Duplication; `docs/plans/milestone-1.md` § What Milestone 1 Does NOT Deliver.

### 5.2 Extrusion recipe structure

- Up to three layers are supported.
- Each layer has a whole-integer thickness ratio; all layer ratios total exactly 100.
- Each layer has its own blend lines.
- A layer's blend percentages total exactly 100.
- Each blend line selects a specific polymer or additive Item.
- The same Item may appear in more than one layer.
- Operationally, a layer usually has 3–4 materials and sometimes about 5, but no hard line limit is intended.
- Estimated consumption is `recipe percentage × (net output + waste)` for the applicable layer.

Sources: `domain-knowledge/po-oc-field-definitions.md` § Extrusion Order Card (OC) Fields > Multi-Layer Extrusion; > Blend Recipe Rules; `domain-knowledge/material-consumption-and-costing.md` § Data Capture Requirements by Business Line > Extrusion.

### 5.3 What the fingerprint represents

`recipe_fingerprint` is intended to prevent output made to different functional recipes from pooling. It uses:

- layer structure and layer percentages;
- normalized `polymer_type`, not the specific polymer Item FK;
- normalized `additive_type`, not the specific additive Item FK;
- blend percentages within each layer.

It is intentionally stable across supplier/grade substitution inside the same normalized material type. It changes when the functional recipe percentage or type changes. Customer is not included.

Sources: `domain-knowledge/production-orders.md` § Recipe Business Rules; `archive/26-F1-identity-key-redesign.md` § Recipe Fingerprint Specification.

### 5.4 Fingerprint implementation remains open

OI-002 still owns:

- canonical fingerprint input and hash construction;
- hash-only versus structured payload plus hash storage;
- additive-color derivation from the stored structure;
- computation timing;
- the database uniqueness/race strategy for `find_or_create_item`.

The repository also lacks a documented fingerprint versioning/migration rule, dominant-polymer tie breaker, duplicate-type aggregation rule, and full null canonicalization contract.

Sources: `reviews-and-questions/open-issues.md` § OI-002: Database Design Rewrite > Recipe fingerprint implementation; `archive/26-F1-identity-key-redesign.md` § Implementation Follow-Ups (Moved to OI-002).

## 6. Inventory, Cost, Receipt, and Traceability Boundaries

### 6.1 Unified Item model

The accepted architecture uses one `Item` table with common relational columns and type-specific JSONB `attributes`, validated in Django. Item also carries valuation state:

- `current_quantity`
- `current_value`
- `last_valid_unit_cost`

Live WAC is derived when current quantity is positive. These valuation fields and receipt costs do not participate in material identity.

Sources: `architecture/decisions/001-jsonb-for-attributes.md` § Decision; `architecture/decisions/003-item-level-inventory-with-wac.md` § Decision > Inventory Model.

### 6.2 Item-level inventory, not lot-level inventory

The stock dimension is Item only. There are no lot balances, FIFO cost layers, per-lot availability, or per-lot price selection. Receipts with different prices update the same Item's WAC if they point to the same Item.

A free-text lot/batch reference can be recorded on Extrusion blend lines for quality investigation. Multiple lots can be entered as text, but the values are not parsed, validated, or linked to received inventory. PP film has no lot field because its producers do not provide lot numbers.

Sources: `architecture/decisions/003-item-level-inventory-with-wac.md` § Decision > Inventory Model; > Lot/Batch on Operation Cards; `domain-knowledge/po-oc-field-definitions.md` § Blend Recipe Rules.

### 6.3 Receipt identity is separate from material identity

Manual raw-material receiving uses a durable `ManualStockReceipt` source record and a paired RECEIPT ledger row. Production output uses `OCReceiptLine` as the durable grouped receipt source, linked to one output Item and one OC.

An `OCReceiptLine` can carry:

- `inventory_item`
- `quantity_kg`
- `value`
- `grade`
- optional `width_mm` identity override
- roll/container counts and tare weights
- computed/overridden `net_quantity_kg`

One OC can have multiple receipt lines, including Prime and B-Grade output or multiple widths. OC + Item cannot uniquely identify a receipt line because one OC can produce the same Item on more than one line.

Sources: `domain-knowledge/inventory-management.md` § Receiving > Manual Stock Receipt; `domain-knowledge/po-oc-field-definitions.md` § Inventory Item Output (All OC Types, All PO Types); `docs/decision-log.md` § Decisions (DL-005, DL-028).

### 6.4 Gross/net and tare do not differentiate the material master

For `film_roll` receipts:

`net_quantity_kg = quantity_kg − (roll_count × core_weight_kg)`

For `bag`/`sheet` receipts:

`net_quantity_kg = quantity_kg − (container_count × container_weight_kg)`

Gross kg is the canonical Item inventory quantity and WAC denominator. Net is a secondary event fact used for backflush, labels, billing/fulfillment, and reporting. Roll counts, container counts, and tare weights describe a receipt group; they are explicitly excluded from Item identity.

Sources: `architecture/decisions/005-inventory-weight-basis-gross-canonical.md` § Key Design Elements > Scope; `domain-knowledge/po-oc-field-definitions.md` § Inventory Item Output (All OC Types, All PO Types); `docs/decision-log.md` § Decisions (DL-002, DL-005).

### 6.5 Physical-unit identity is not currently present

Current inventory pools output by Item and grouped receipt line. It does not assign a persistent ID to every physical roll, bag, sheet, pallet, or outer container.

Later plans consider `OutputRoll` records with label/roll ID, exact gross/net/core weight, width, length, destination, status, location, and optional parent-roll linkage, plus analogous `OutputContainer` detail. The exact granularity is still open. Barcode scanning is out of M1, and label content/timing for intermediate inventory remains an implementation-time gap.

Sources: `docs/plans/milestone-2.md` § Per-Roll vs. Aggregate Inventory Operations; `docs/plans/milestone-3.md` § Open Questions; `reviews-and-questions/oi-012-triggered-findings.md` § R3-11: Physical Labeling Workflow for Intermediate Inventory; `docs/plans/milestone-1.md` § What Milestone 1 Does NOT Deliver.

### 6.6 Pooled Item identity is not end-to-end genealogy

Transactions retain source OC and receipt references, but downstream consumption from a pooled Item does not identify which exact upstream receipt or roll supplied the material. OI-014 remains open on whether to add OC-level or receipt-line-level provenance. Full lot trace-forward/trace-back and regulatory requirements are not resolved.

Sources: `reviews-and-questions/open-issues.md` § OI-014: Intermediate Item Provenance / Source Tracking; `reviews-and-questions/oi-012-triggered-findings.md` § OI-014: Intermediate Item Provenance; `architecture/erp-module-map.md` § Unresolved Scope Questions > Regulatory & Compliance.

### 6.7 Item lifecycle preserves identity history

Every material/output Item has `is_active`, defaulting to true. Hard deletion is allowed only when an Item has never been referenced by a stock transaction or OC. Otherwise it is deactivated, remains visible in history, and can later be reactivated. A discontinued grade therefore retains its database identity and historical relationships instead of being erased.

This matters for a future business number: the repository's lifecycle assumes continuity through deactivation/reactivation, although it never explicitly states a code immutability rule.

Source: `domain-knowledge/master-data.md` § Item Lifecycle (Active / Inactive).

## 7. Material Flow and Intended Use

### 7.1 As-is baseline before the ERP design

Before the proposed ERP, production was driven by one Excel technology card per operation. Repeated work was created by copying earlier files. Cards carried shared product descriptions plus operation-specific facts such as Extrusion blend ratios and Printing ink colors.

Material storage was ad hoc; issue to production was not recorded; reordering depended largely on staff memory; and discrepancies were written off. Extrusion recorded finished kg rather than actual inputs, Printing refilled ink/solvent without measuring per job, Confection recorded no material input, and waste was not captured systematically. This explains why the repo begins with descriptive names and Item-level reconciliation rather than a clean legacy material-number/lot master.

Source: `docs/as-is-state-pre-erp.md` § Production Orders; § Inventory Management; § Material Consumption and Costing.

### 7.2 Receiving and storage

Raw and purchased material enters through manual stock receipt: select the Item, enter quantity in kg, receipt value/cost, and date. There is no purchasing/order match, structured Supplier entity, lot-controlled receipt, or location tracking. Supplier is currently free text.

Sources: `domain-knowledge/inventory-management.md` § Receiving; § Storage; `domain-knowledge/master-data.md` § Suppliers.

### 7.3 Extrusion

Extrusion consumes exact polymer/additive Item FKs on recipe blend lines. Workers can write the batch/lot reference on the paper OC, but inventory consumption and costing remain Item-level. Output is a `film_roll`, automatically resolved from the nine-attribute identity key.

Source: `domain-knowledge/po-oc-field-definitions.md` § Extrusion Order Card (OC) Fields; `domain-knowledge/material-consumption-and-costing.md` § Data Capture Requirements by Business Line > Extrusion.

### 7.4 R&S, Printing, and Confection

Each non-Extrusion OC consumes a selected `material_input` Item and a gross `input_quantity_kg`. R&S changes width/form/gusset where specified; Printing adds `print_project` and references up to eight ink Items; Confection converts roll film to bag, sack, or sheet with its structured dimensions/features.

Source: `domain-knowledge/po-oc-field-definitions.md` § Material Input Field; § Input Quantity Field; §§ Printing, Rewinding & Slitting, and Confection Order Card Fields.

### 7.5 Output, stock, and downstream reuse

Every Completed OC receipts good output. Intermediate output can be consumed by the next OC in the same PO or selected by a new PO. Surplus and internal/MTS production enter the same stock pool. Rework uses a new PO rather than changing the source Item in place.

Sources: `domain-knowledge/master-data.md` § Category 6: Film Products (Production Output) > Purpose; `domain-knowledge/production-orders.md` § Rework; § Internal POs.

### 7.6 Waste and recycling

Current production capture uses one `waste_weight_kg` total per OC. That number can contain purge, trim, off-spec material, and other non-good output. Current canonical inventory wording creates a zero-cost waste/scrap receipt, but OI-015 says the final material taxonomy and receipt/disposition mechanism are not settled.

The working direction distinguishes:

1. Simple capture of non-output material at OC closeout.
2. Later explicit classification/disposition as true waste, scrap for sale, recoverable/recyclable material, or possibly rework.

Potential identity dimensions under discussion include polymer/material family, printed/contaminated state, and source process. None is approved. A historical proposal of `material_type + contaminated` is not a final key.

Sources: `domain-knowledge/material-consumption-and-costing.md` § Waste Definition; `domain-knowledge/inventory-management.md` § Waste Receipt; `reviews-and-questions/oi-015-waste-model-working.md` § Proposed Two-Stage Model; § Main Design Questions OI-015 Must Answer; § Working Conclusion.

Future recycling is intended to consume a waste/scrap Item through an Internal PO and produce `Recycled LDPE` back into inventory once the necessary equipment exists.

Source: `docs/plans/deferred-functionality.md` § Scrap Recycling via Internal PO.

## 8. Historical, Prototype, and Experimental Evidence

This section is intentionally subordinate to current canonical documents.

### 8.1 Early inventory preparation

The early inventory checklist explicitly asked how raw materials should be identified—by code, name, supplier SKU, or another method—and whether finished goods should be customer-specific or generic. This confirms that the question was recognized, not that an internal number was chosen. The later answer became descriptive display name plus database PK.

Source status: historical/superseded. Source: `archive/18-inventory-module-prep.md` § Category 1: Domain Knowledge to Document > Master Data Domain; § Recommended Sequence: Documentation Sessions > Session 1: Raw Material Catalog; § Remaining Questions.

### 8.2 Archived roll/barcode conclusion

An early archived Q&A said individual roll stickers/barcodes were not planned. Later current documents require dispatch/intermediate labels and keep per-roll identity as deferred work, so the archive cannot be used as the current rule. It does show that a barcode was considered a physical-unit mechanism, not a material-master number.

Source status: historical and partly superseded. Source: `archive/06-material-blending-pantone-tolerance-answers.md` § 2. Roll Identity: Physical Stickers/Barcodes on Every Roll?; current contrast: `domain-knowledge/operational-procedures.md` § Dispatch — Film Rolls > Labeling Requirement; `docs/plans/milestone-3.md` § Open Questions.

### 8.3 Printing discovery notes

Early printing notes captured that the input is flexible PE/PP film, the process can use many inks and several solvents, supplier containers are partially consumed, refills are not weighed, and different inks can vary substantially in cost. These facts support separate ink/solvent Items and later weigh-in/weigh-out, but they provide no code scheme.

Source status: historical raw discovery, later distilled into current documents. Source: `archive/07-printing-process-early-notes.md` § Materials; § Current Material Handling Process; § Cost Variability.

### 8.4 Archived identity-key redesign

The archived F1 design record is useful provenance for the current `film_roll` key:

- `stage_completed` was removed because physical specifications already distinguish the result.
- `color` was removed as a stored key because recipe data subsumes it.
- `side_gusset_depth_mm` and `recipe_fingerprint` were added.
- `material_type` was restored to prevent BOPP and CPP from pooling when no Extrusion fingerprint exists.
- Specific material FKs were excluded from the fingerprint to tolerate supplier-grade substitution.

These conclusions were propagated to current canonical files. The archive itself should not be implemented in preference to those files.

Source: `archive/26-F1-identity-key-redesign.md` § New Identity Key; § Attributes Removed; § Attributes Added; § Recipe Fingerprint Specification; § Decision Log.

### 8.5 Inventory UI prototype

The transient inventory prototype proposed type keys such as `pe_polymer`, `purchased_film`, `additive`, `ink`, `solvent`, and `wip`. It used a common required `name`, contained sample material names, and modeled WIP as manually created with source PO/stage fields.

That prototype is stale in important ways:

- Current output types are `film_roll`, `bag`, and `sheet`, not a single WIP type.
- Current output Items are automatically found/created from semantic keys rather than manually created.
- Source stage/PO is not Item identity.
- Prototype sample names are UI fixtures, not a confirmed factory material catalog.

Source status: transient/non-authoritative. Source: `tmp/prototype/inventory-module-spec.md` § Material Types in the System; § Screen 3: New Item Form; § Per-Type Detail Examples.

### 8.6 Archived process viewer

The archived process-viewer JSON sometimes says “Material ID” and models alternative-material selection, individual roll weights, and product flow. It does not define the shape or generation of that ID. The viewer is explicitly archived because domain documents are authoritative; some process folders are placeholders.

Source status: historical/archived. Sources: `archive/README.md` (entry 37); `archive/37-processes-viewer/extrusion/nodes.json` (material-availability and alternative-material nodes).

### 8.7 Superseded customer-specific finished-good code

An explicitly stale database-design snapshot modeled Item types as `raw_material`, `purchased_component`, `wip`, and `finished_good`. Its finished-good example contained:

- a customer-specific name, `Customer ABC - 100μm printed film`;
- a `customer` attribute;
- `product_code = FG-ABC-001`.

This is real evidence that a product-code field was considered, but it is not a surviving decision. The entire file is archived as stale, and the example conflicts with later rules in several ways: current output is `film_roll`/`bag`/`sheet`, customer is excluded from identity, thickness is stored in millimeters, lifecycle stage is not an Item type, and no internal SKU is defined.

Source status: explicitly stale/superseded. Source: `archive/15-database-design-stale.md` § Item Table (Unified Inventory); `archive/README.md` (entry 15).

### 8.8 ERPNext test handoff

The transient ERPNext test proposes a second visible Item-code pattern:

- An early test manufactured Item was likely named/code-like as `KAM-FILM-LDPE-LLDPE-AS-80-15-5`.
- The handoff suggests a better future pattern: opaque `KAM-FILM-001` as the code, with specification details in fields and the display name.
- Raw test Items were `LDPE Test`, `LLDPE Test`, and `Additive Test`.
- The test BOM was `BOM-KAM-FILM-LDPE-LLDPE-AS-80-15-5-001`.
- It states that manufacturer/grade-specific raw materials should be separate ERPNext Items when those distinctions matter, with ERPNext Item Alternatives considered for interchangeable materials.

This is **not** an approved number for the custom ERP. It also contains a major model difference:

- Custom ERP canonical design: customer is not Item identity; identical specifications and recipes pool across customers.
- ERPNext test direction: manufactured Items are described as customer-specific.

The new project must choose which rule it wants before adopting the test code pattern.

Source status: transient experiment/handoff. Source: `tmp/erpnext-test-handoff.md` § ERPNext Terminology Mapping; § Current ERPNext Test Data / Actions; § Specific Explanations Already Given.

### 8.9 Raw interview and spreadsheet-mapping evidence

The raw discovery material adds several practical facts that matter for future search, aliases, and label design:

- Workers historically used short or ambiguous names such as “Sabic,” “Petilen,” “hard,” and “soft,” while the intended master uses full manufacturer/type/grade names.
- For first-operation purchased PP stock, BOPP/CPP plus width was historically enough for the shift manager because there were few producers and only four or five standard sizes. This explains the simple operational naming, but it is weaker than the full characteristic set required by the future Item model.
- Within a PO, workers locate upstream material by PO number rather than recording the upstream OC ID. This is a source-location practice, not a material-master identity rule.
- PO duplication copies exact material references and blend ratios; a shift manager can substitute another Item of the same functional type when the original is unavailable.
- `print_project` is a named artwork identifier; examples in interview notes include `Summer Green` and `Gold`. Operators locate physical plates by customer folder plus project name.
- Historical ink notation combined color/formulation and anilox. The to-be mapping separates an ink Item FK from anilox text. Known anilox values found in the spreadsheet analysis include 110, 220, 240, 255, and 300.
- Clean trim is operationally regarded as recyclable rather than true waste, even though the current capture field combines non-good output.

Sources are raw/non-authoritative but consistent with later canonical design: `tmp/interview/interview-12-02-2026.md` § Duplication Logic; § Rework — What Happens When Production Output is Bad?; `tmp/interview/interview-18-02-2026.md` § New Field: Print Project; `tmp/interview/interview-26-02-2026.md` § Q5: When operations chain, does Elena track which material feeds into which step?; § Q8: Blend ratio edge cases — duplicates and rounding; `tmp/excel-to-erp-field-mapping.md` § Inks / Solvents Configuration → Ink Stations.

### 8.10 Prototype-only example catalog

The inventory prototype contains realistic example rows that may be useful when locating old spreadsheets or preparing a migration extract:

- `Rom Petrol LDPE B20/O.3`
- `SHELL LLDPE 18F1B`
- `PETILEN PE 0321T`
- `Recycled LDPE (Plastchim-T)`
- `BOPP PLCBZ25 960mm`
- `CPP XK318 1200mm`
- `Polybatch VOA 66`
- `Blue AGL 4535`
- `Red 485B`
- `Ethyl Acetate`

These are prototype fixtures, not a verified current factory catalog. They should be treated as search clues only.

Source status: transient/non-authoritative. Source: `tmp/prototype/inventory-module-spec.md` § Screen 1: Inventory List; § Per-Type Detail Examples.

## 9. What the Current Project Planned to Build

### 9.1 Initial custom ERP scope

The M1 plan includes:

- Item CRUD for PE polymers, PP films, additives, inks, solvents, and `film_roll`/`bag`/`sheet` output;
- one unified Item model with type-specific JSONB validation and forms;
- item-level stock and WAC;
- manual stock receipt;
- exact-Item recipe/input selection;
- automatic output Item matching/creation through `find_or_create_item`;
- grouped production receipt lines;
- calculated reservations and monthly reconciliation;
- Item deactivation rather than deletion after use.

Sources: `docs/plans/milestone-1.md` § What Milestone 1 Delivers; § Implementation Sequence > Phase 2b: Master Data — Items; > Phase 5: Production Orders; `architecture/decisions/001-jsonb-for-attributes.md` § Decision.

### 9.2 Explicitly deferred or unresolved

- Business material/SKU numbering: not planned in the custom ERP documents.
- Barcode scanning.
- Full supplier lot/batch traceability.
- Individual-roll/container identity and per-roll inventory operations.
- Multi-location/warehouse-bin identity.
- Structured purchasing and supplier master.
- Structured Recipe/BOM library.
- Structured Customer Print Project.
- Per-job ink/solvent measurement.
- Full quality-control specifications and batch genealogy.
- Purchased-component tracking.
- Waste/scrap taxonomy and identity.
- Purchased recycled LDPE naming.

Sources: `docs/plans/milestone-1.md` § What Milestone 1 Does NOT Deliver; `docs/plans/deferred-functionality.md` §§ Inventory, Production, Printing, Quality Control Module, Purchasing Module; `reviews-and-questions/open-issues.md` §§ OI-014, OI-015, OI-002.

## 10. Unresolved Issues and Contradictions Relevant to Material Numbering

### 10.1 Identifier-grain questions

1. The requested “material number” has not yet been assigned an explicit grain: reusable Item specification, supplier lot, production receipt/batch, or individual physical stock unit.
2. The prior “no internal SKU” decision would need to be reversed or narrowed if the new project requires a stable business-facing number.
3. No field exists for legacy code, supplier code namespace, external-system code, barcode value, or cross-system identifier.
4. Renaming, number immutability, reuse after deactivation, merge/split of duplicate Items, and migration of existing Items are not specified.

### 10.2 Raw/purchased Item uniqueness gaps

1. No formal per-type semantic key or database uniqueness constraint exists for PE, PP, additives, inks, or solvents.
2. PP's display name omits several required characteristics that could distinguish stock.
3. Additive “SKU” means product name, not an internal SKU field.
4. Ink and solvent names have no normalization or duplicate-prevention contract.
5. Supplier, producer, and manufacturer are text rather than controlled master records.
6. Purchased recycled LDPE naming remains deferred.
7. Generic solvent values remain to be cleaned/classified.
8. Cores and packaging do not yet have a material-master design.

### 10.3 Produced Item uniqueness gaps

1. The semantic keys are defined, but the database unique-constraint and concurrent `find_or_create_item` strategy remain open under OI-002.
2. The auto-generated output display-name grammar is incomplete.
3. `recipe_fingerprint` serialization, storage, timing, and versioning are incomplete.
4. Free-text `print_project` remains identity-bearing; whitespace/case normalization cannot prevent spelling variants or renamed designs from fragmenting Items.
5. `grade` says both “Prime default” and “null = prime.” Without one canonical storage representation, null and `Prime` could create duplicate keys.
6. `treatment` is optional but also has an explicit `None` choice; null versus `None` canonicalization is unstated.
7. No dominant-polymer tie-break rule is documented.
8. The PP-to-output attribute-name mapping is unstated.
9. The stale database-design precision table cannot represent documented `thickness_mm` values such as `0.025` if dimensions use only one decimal place. Applying it would collapse distinct materials.

Sources: `reviews-and-questions/open-issues.md` § OI-002: Database Design Rewrite; § Phase-Gated Decisions > Phase 5; `domain-knowledge/master-data.md` § Category 6: Film Products (Production Output); `architecture/database-design.md` § Decimal Precision by Value Category; `domain-knowledge/po-oc-field-definitions.md` § Extrusion Order Card (OC) Fields > 5. Thickness.

### 10.4 Taxonomy gaps

1. HDPE/EVA appear in one polymer list but not in the current raw/output identity choices.
2. `grade` means supplier product grade for raw items and Prime/B-Grade quality class for output.
3. Waste/scrap has no approved Item branch or key.
4. “Waste” capture currently combines material that may later be true waste, sellable scrap, recyclable material, or rework.
5. The commercial `product_category` list does not equal the material taxonomy and cannot identify waste.

### 10.5 Lot and traceability conflicts

1. ADR-003 says lots are OC references only, while additive and recycled-LDPE wording still suggests optional lot data in the material area.
2. Full material genealogy through pooled intermediate Items is open.
3. Regulatory need for trace-forward/trace-back remains unresolved.
4. A material-master number alone would not solve any of these source-lot or physical-unit problems.

### 10.6 Planning/documentation drift

Several current plan/working texts have not fully propagated later decisions, including explicit versus automatic downstream input selection, receipt-line width override scope, tare-field requirements, and production-output reconciliation wording. The canonical domain/ADR rule should control where this report states an established fact. OI-017 is intended to convert the repository into more declarative, implementation-ready specifications before the OI-002 schema rewrite.

Sources: `reviews-and-questions/lifecycle-d1-material-input-auto-fill.md` § Propagation Notes; `docs/decision-log.md` § Decisions (DL-005); `reviews-and-questions/open-issues.md` § OI-017: Documentation Quality Pass — Agent-Ready Specifications.

### 10.7 Item-selection inconsistency

The current Item lifecycle section says the goods-receipt selector shows only Items with both `is_active = true` and stock greater than zero. That would hide an active zero-stock Item precisely when receiving replenishment, despite separate wording that an out-of-stock Item may be reordered. This is a verified workflow contradiction. It is not a numbering decision, but it will affect whether users create accidental duplicate Items instead of finding and replenishing the existing material.

The same lifecycle prose calls the balance `current_stock`, while ADR-003 defines the valuation field as `current_quantity`; the schema rewrite should select one canonical field name.

Sources: `domain-knowledge/master-data.md` § Item Lifecycle (Active / Inactive) > Dropdown Visibility (Two-Filter Rule); > PO Duplication with Unavailable Materials; `domain-knowledge/inventory-management.md` § Receiving; `architecture/decisions/003-item-level-inventory-with-wac.md` § Decision > Inventory Model.

## 11. Information Worth Carrying into the New MES/MRP Project

The following are not a new numbering decision. They are the strongest reusable requirements extracted from the prior work.

### 11.1 Preserve separate identity layers

The new project should make separate decisions for:

1. **Material master:** reusable raw/product specification.
2. **Supplier lot/batch:** one procurement/production batch where traceability requires it.
3. **Receipt/production batch:** one inventory event and its source.
4. **Physical stock unit:** individual roll, pallet, or container if operational scanning is required.
5. **Commercial/work records:** CO, PO, OC, BOM, and route identifiers.

The old repo intentionally solved these at different grains. Combining them into one “unique material number” would discard useful distinctions.

### 11.2 Reuse the established material taxonomy, subject to cleanup

Start from PE polymer, purchased PP film, additive, ink, solvent, purchased component, `film_roll`, `bag`, `sheet`, and waste/recyclable material. Before implementation, reconcile HDPE/EVA, purchased recycled LDPE, generic solvent, components, and waste.

### 11.3 Reuse the output semantic keys

The 9/14/7 attribute sets are the most mature definition in the repository of when two produced materials are interchangeable enough to share stock. Even if the new project gives each Item an opaque code, those attributes remain necessary as:

- duplicate-prevention criteria;
- product/specification fields;
- search and display data;
- BOM/routing compatibility inputs;
- migration matching rules.

### 11.4 Decide raw-material natural keys explicitly

The prior work suggests likely identity ingredients but never makes them constraints:

- PE: manufacturer + normalized polymer type + producer grade.
- PP: film type + producer + product/grade code + width + thickness + treatment + film form.
- Additive: supplier/manufacturer + product/brand code + functional type, with color/form where material.
- Ink: formulation/product code + supplier/manufacturer, with color as a search/display property.
- Solvent: controlled chemical/product identity + supplier/manufacturer where commercial grade matters.

These are evidence-derived candidates, not approved keys. The new project must validate them against actual labels, invoices, certificates, and interchangeability rules.

### 11.5 Keep code separate from mutable description

The stale `FG-ABC-001` example and the ERPNext test's `KAM-FILM-001` idea are the only explicit business-code patterns found. The former encoded customer context; the latter suggests an opaque stable code with specifications in fields/name. Both are non-authoritative. If the new project follows either direction, it should be treated as a new decision, not as prior approval.

### 11.6 Carry forward deliberate non-identity rules

Unless the new project deliberately changes the product model, do not encode these into the material number or uniqueness key:

- customer;
- PO/OC route stage;
- current WIP/final intention;
- cost or supplier receipt price;
- quantity/tare;
- physical roll count;
- specific supplier Item used in a functionally equivalent recipe substitution.

### 11.7 Resolve the custom-ERP versus ERPNext product-grain conflict

The new project must choose between:

- one Item per physical specification/recipe, pooled across customers; or
- separate customer-specific manufactured Items.

That choice changes Item counts, BOM ownership, number generation, duplicate rules, stock substitutability, labels, and migration. The repository currently contains both directions, but only the first is canonical for the custom ERP.

## 12. Direct Answers to the Research Questions

### How have raw materials been defined?

As unified Item records divided into PE polymers, purchased PP films, additives, inks, and solvents, with category-specific descriptive attributes. Cores/packaging are identified as a future category but not designed. Raw stock is received and valued by Item in kg, with no lot or location stock dimension.

### What types of raw materials have been defined?

PE resin types, BOPP/CPP purchased film, five functional additive groups, formulated inks, and named solvents. Purchased recycled LDPE exists conceptually; in-house inline regrind is intentionally invisible. Waste/recyclable material is not yet a finalized type.

### Has a way to uniquely identify raw materials been defined?

Only partially. PE and PP have display-name conventions and a technical database PK. Additives, inks, and solvents have descriptive names/attributes. None has an approved business material number or a documented formal composite uniqueness key.

### Has a unique inventory number been defined?

No. The current custom ERP decision is display name plus database PK, with no internal SKU. The only proposed human-facing code examples found are the superseded `FG-ABC-001` example and the non-authoritative ERPNext test example `KAM-FILM-001`.

### Have key material characteristics been defined?

Yes, substantially. Raw/purchased characteristics are listed by category, and production outputs have exact 9/14/7 semantic identity keys. Important gaps remain in normalization, allowed-value alignment, technical-data collection, raw uniqueness, print-project structure, fingerprint implementation, components, and waste.

### How are final materials/final output defined?

By physical form (`film_roll`, `bag`, `sheet`) and exact semantic attributes, not by customer or lifecycle stage. Every Completed OC receipts output to inventory, where matching identity keys pool. The same Item can be intermediate in one route and final/dispatchable in another.

### What was planned to be done with this information?

The custom ERP planned to use it for Item CRUD, exact input selection, recipes on OCs, calculated reservation, backflush/consumption, automatic output Item creation, WAC inventory, receipt grouping, downstream reuse, dispatch, and reporting. Business numbering, individual-roll identity, full lot traceability, purchasing, structured BOMs, and several supporting masters were not part of the approved first implementation.

## Conclusion

The prior work provides a strong **material-specification and pooling model**, especially for in-house output. It does not provide a **material-number model**.

The new MES/MRP project can reuse the category definitions, raw characteristics, exact output keys, recipe normalization rules, and identity exclusions. It should not assume that the existing database PK, display name, lot reference, PO/OC number, or recipe fingerprint is already the requested unique material number. Choosing that number remains a new design decision, and it should begin by selecting the identifier grain and resolving the raw-material, waste, physical-unit, and customer-specific-product gaps documented above.
