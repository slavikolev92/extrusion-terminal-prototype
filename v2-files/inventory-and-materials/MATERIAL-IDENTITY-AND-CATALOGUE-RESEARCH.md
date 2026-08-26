# Material Identity And Catalogue Research

Status: completed research input for the future combined material-master design.

Date: August 15, 2026.

This document records the research conducted while refining Task 20, **Editable
Executed Recipes And Material Catalogue**. It is deliberately separate from the
Task 20 specification. It does not by itself amend Task 20, approve a database
schema, or authorize implementation. It is intended to be compared with the
material-identification work from the other project before one combined design
and recommendation is written.

## 1. Research Question

The immediate question was how the extrusion terminal should identify raw
materials so that:

- a material can be renamed without losing its identity;
- different processes can display different familiar names for the same
  material;
- recipes can refer unambiguously to the material that was planned and used;
- the future inventory application can communicate with the Shift Manager
  workbook, extrusion terminal, costing tools, and other production processes;
- supplier codes, manufacturer codes, barcodes, batches, and old names do not
  become unreliable substitutes for a permanent material identity;
- the current CSV-based catalogue can later be replaced by an API without
  redesigning recipe and production history; and
- the design remains proportionate to the small pilot application.

The specific research request was to examine how ERPNext, Odoo, other ERP and
MRP products, inventory applications, and relevant standards solve this
problem, then recommend the most durable pattern for this project.

## 2. Research Method

The review used primary sources only: official product documentation, official
vendor source repositories, and official GS1 standards material. The systems
reviewed were:

- ERPNext/Frappe;
- Odoo;
- SAP S/4HANA;
- Microsoft Dynamics 365 Supply Chain Management;
- Oracle Fusion Cloud SCM;
- MRPeasy;
- Katana; and
- GS1 identification standards.

The review compared the following concerns across systems:

1. the record that represents a material or stockable item;
2. the identifier used for that record;
3. generated versus manually assigned numbering;
4. the difference between identifier, name, description, and category;
5. product-family and concrete-variant identity;
6. manufacturer, supplier, customer, legacy, and source-system references;
7. barcode and GTIN handling;
8. units of measure;
9. deactivation, obsolescence, and deletion;
10. batch, lot, and serial traceability;
11. substitutions and related items; and
12. CSV/API synchronization consequences.

## 3. Executive Conclusion

The systems differ in terminology and implementation, but the underlying
pattern is consistent:

> A material or item has a stable internal identity. Names, descriptions,
> categories, supplier numbers, manufacturer numbers, barcodes, GTINs, and
> batch/lot numbers are separate attributes or identifiers attached to it.

The current Task 20 specification conflicts with that pattern because it says
that `FullMaterialName` is the canonical catalogue identity. A name is editable
business data and should not be the permanent link between recipes, inventory,
costing, and production applications.

The provisional recommendation from this research is therefore:

1. Give every material an immutable, machine-owned `material_id`.
2. Give it a permanent, unique, human-usable `material_code`, such as
   `MAT-000001`.
3. Keep the code deliberately non-semantic: do not encode category, producer,
   grade, year, or process in it.
4. Store names, categories, producer, brand family, grade, UOM, and lifecycle
   status separately.
5. Store external identifiers such as supplier code, manufacturer part number,
   GTIN, barcode, old name, ERPNext Item Code, or Odoo ID as typed aliases.
6. Treat exact inventory variants as separate coded materials when they must be
   stocked, consumed, costed, approved, or traced separately.
7. Keep batches/lots and serial numbers separate from material identity.
8. Deactivate material records instead of deleting or reusing them.
9. Store the permanent material reference plus human-readable snapshots on an
   executed recipe.
10. Use the same material contract for CSV now and API synchronization later;
    only the transport and authoritative source should change.

This recommendation is intentionally provisional until it is reconciled with
the other project's earlier work.

## 4. Findings By System

### 4.1 ERPNext And Frappe

ERPNext uses an **Item** master for products, services, raw materials,
subassemblies, finished goods, and variants. Its central business identifier is
the **Item Code**. The Item Name, Item Group, Stock UOM, Brand, description, and
other commercial or operational data are separate fields.

The standard Item document is named from `item_code`, and a Frappe document's
`name` is its unique primary key. ERPNext therefore uses the Item Code as both a
business identifier and the normal link/API locator for an Item.

Important characteristics are:

- Item Code is required and unique.
- Item Name is a human-facing name and is not the identity.
- Item Codes can be entered manually or generated by a naming series.
- Item Codes can be renamed, including through bulk rename; ERPNext updates
  references during its governed rename operation.
- Item Group, Brand, description, and UOM are separate master data.
- Supplier item codes are stored in a supplier relationship, not used as the
  internal Item Code.
- Manufacturer and manufacturer part number are stored as a separate
  relationship and can support multiple manufacturer mappings.
- An Item can have multiple barcodes; a barcode is an operational lookup alias,
  not the Item's primary identity.
- Customers can have their own reference codes for an Item.
- Disabled or end-of-life Items are retained but prevented from normal future
  transactions.
- Item Alternatives are explicit relationships used for permitted
  substitution.
- Batches and serial numbers are traceability records for an Item, not the Item
  identity itself.

ERPNext also distinguishes an Item template from a concrete variant. A template
marked as having variants cannot itself be used in normal transactions; the
concrete variant is the transactable Item. That supports the rule that the
integration identity must belong to the exact material that is stocked or used,
not merely to a product family.

ERPNext demonstrates both the value and limitation of a business code. Its Item
Code is a strong operational identifier, but it is intentionally renamable. A
source-neutral integration should therefore retain its own immutable identity
and treat an ERPNext Item Code as an external identifier whose rename history
can be preserved.

Sources:

- [ERPNext Item](https://docs.frappe.io/erpnext/item)
- [ERPNext Item schema](https://github.com/frappe/erpnext/blob/develop/erpnext/stock/doctype/item/item.json)
- [Frappe document naming](https://docs.frappe.io/framework-copy/user/en/basics/doctypes/naming)
- [ERPNext Item controller](https://github.com/frappe/erpnext/blob/develop/erpnext/stock/doctype/item/item.py)
- [ERPNext Bulk Rename](https://docs.frappe.io/erpnext/bulk-rename)
- [ERPNext Item Variants](https://docs.frappe.io/erpnext/item-variants)
- [ERPNext Manufacturer](https://docs.frappe.io/erpnext/manufacturer)
- [ERPNext supplier part numbers](https://docs.frappe.io/erpnext/maintaining-suppliers-part-no-in-item)
- [ERPNext Item Alternative](https://docs.frappe.io/erpnext/item-alternative)
- [ERPNext Serial and Batch](https://docs.frappe.io/erpnext/serial-and-batch)
- [Frappe Data Import](https://docs.frappe.io/erpnext/data-import)
- [Frappe REST API](https://docs.frappe.io/framework/user/en/guides/integration/rest_api)

### 4.2 Odoo

Odoo has two important catalogue levels:

- `product.template` represents the shared product definition or family; and
- `product.product` represents a concrete variant.

The concrete `product.product` variant is the relevant identity when stock,
recipes, purchasing, or consumption must distinguish one exact material from
another. Each Odoo record has a database ID, but that ID is local to a
particular Odoo database. Odoo can also have an External ID/XML ID for portable
import and integration references.

Odoo's **Internal Reference** (`default_code`) is a searchable business code at
the concrete variant level. However, standard Odoo warns about a duplicate
Internal Reference rather than enforcing database uniqueness. It should not be
assumed to be a globally unique synchronization key.

Other significant findings are:

- Product Name is required, editable, and translatable; it is presentation
  data, not stable identity.
- Display names can combine a product name, Internal Reference, variant
  attributes, and supplier-specific information depending on context.
- Vendor product name and Vendor Product Code are separate rows associated with
  a vendor and optionally a concrete variant.
- Barcode is attached to the concrete variant and is constrained within the
  appropriate company scope, but it remains a scanner-facing identifier rather
  than a source-neutral material identity.
- Product category and attribute values organize and describe products but are
  not identifiers.
- The product UOM is an explicit reference used for stock operations.
- `active=False` archives a product without removing its historical use.
- Lots and serials are separate traceability records belonging to a product.
- A variant's lifecycle is not necessarily immutable: changing attributes may
  archive or recreate unused variants. A local integration must not assume that
  an attribute combination or Odoo database ID is a permanent universal
  material identity.

Odoo is particularly useful for demonstrating why one should not use a display
name, Internal Reference, barcode, vendor code, or database ID from an external
system as the sole permanent cross-application key. The local material master
should retain its own identity and store Odoo instance, model, record ID,
External ID, and change timestamp as source-system metadata.

Sources:

- [Odoo product variants](https://www.odoo.com/documentation/19.0/applications/sales/sales/products_prices/products/variants.html)
- [Odoo product variant source](https://github.com/odoo/odoo/blob/19.0/addons/product/models/product_product.py)
- [Odoo product template source](https://github.com/odoo/odoo/blob/19.0/addons/product/models/product_template.py)
- [Odoo vendor product information source](https://github.com/odoo/odoo/blob/19.0/addons/product/models/product_supplierinfo.py)
- [Odoo import and External ID documentation](https://www.odoo.com/documentation/19.0/applications/essentials/export_import_data.html)
- [Odoo units of measure](https://www.odoo.com/documentation/19.0/applications/inventory_and_mrp/inventory/product_management/configure/uom.html)
- [Odoo lots](https://www.odoo.com/documentation/19.0/applications/inventory_and_mrp/inventory/product_management/product_tracking/lots.html)
- [Odoo serial numbers](https://www.odoo.com/documentation/19.0/applications/inventory_and_mrp/inventory/product_management/product_tracking/serial_numbers.html)
- [Odoo JSON-2 external API](https://www.odoo.com/documentation/19.0/developer/reference/external_api.html)

### 4.3 SAP S/4HANA

SAP uses a material or product number as the central identifier. Number ranges
can support internally assigned numbers and externally supplied numbers. The
material/product type controls parts of the master-data behavior, while
description, material group, base UOM, manufacturer data, GTIN, status, batch
management, and serial settings remain separate.

Relevant SAP patterns include:

- Material numbers are centrally governed identifiers.
- Descriptions may be language-specific and are not identity.
- Material type and material group classify the record.
- Manufacturer part number is not safe by itself; the manufacturer and its part
  number form the meaningful external reference.
- An old product number can be retained as a cross-reference.
- GTIN/EAN/UPC values are associated with packaging or UOM context.
- Batch and serial control are separate inventory/traceability concerns.
- Obsolete products use status, blocking, deletion flags, and controlled
  archival rather than casual hard deletion.
- Product substitution is an explicit relationship with direction, priority,
  status, effective dates, and possibly conversion factors.

SAP supports the core conclusion that the material number should not encode all
descriptive meaning and that external references, traceability, status, and
substitution need their own structures.

Sources:

- [SAP material numbers](https://help.sap.com/docs/SAP_S4HANA_ON-PREMISE/91b21005dded4984bcccf4a69ae1300c/977cbd534f22b44ce10000000a174cb4.html)
- [SAP material type and number ranges](https://help.sap.com/docs/s4hana-best-practices/create-product-master-of-type-finished-good-bnt-858a189be16d19136476a664ab4de3a0/material-type-and-number-ranges)
- [SAP product master areas](https://help.sap.com/docs/SAP_S4HANA_CLOUD/f86dc2eb1f8b48c880a7607213104b27/46c3b853dcfcb44ce10000000a174cb4.html)
- [SAP manufacturer part number](https://help.sap.com/docs/SAP_S4HANA_ON-PREMISE/36802406aebb4b96b1598246e1d316ee/2dd8c353b677b44ce10000000a174cb4.html)
- [SAP Product Master Data API](https://help.sap.com/docs/SAP_S4HANA_CLOUD/3c916ef10fc240c9afc594b346ffaf77/2c973258fb9d2060e10000000a44147b.html)
- [SAP product substitution](https://help.sap.com/docs/SAP_S4HANA_CLOUD/32da8359c8ee4e8b8e8c5e15cacba5aa/794236414c5f4dc5ae8dd0ebce9c237d.html)

### 4.4 Microsoft Dynamics 365 Supply Chain Management

Dynamics distinguishes a globally shared **product number** from a
legal-entity-specific item number. Microsoft recommends using the unique
product number as the primary identifier wherever possible because divergent
legal-entity identifiers make supply-chain tracing and integration harder.

Dynamics also separates:

- product number from product name, description, and search name;
- shared product from the released product used by a particular legal entity;
- product master from concrete product variants;
- global product number from legal-entity item number;
- internal identity from vendor, customer, external, barcode, and GTIN codes;
- product identity from tracking dimensions such as batch and serial; and
- product identity from lifecycle state.

Product variants can be combinations of configuration, color, size, style, and
version. Dynamics recommends a unique product number for a variant instead of
requiring every integration to combine an item number with several dimension
values.

GTINs can be maintained per product and UOM because different packaging levels
can have different GTINs. External codes also have an explicit code type and
scope. This is strong evidence that one untyped text field cannot correctly
represent all identifiers associated with a material.

Sources:

- [Dynamics product identifiers](https://learn.microsoft.com/en-us/dynamics365/supply-chain/pim/product-identifiers)
- [Dynamics product information overview](https://learn.microsoft.com/en-us/dynamics365/supply-chain/pim/product-information)
- [Dynamics product dimensions](https://learn.microsoft.com/en-us/dynamics365/supply-chain/pim/product-dimensions)
- [Dynamics product lifecycle states](https://learn.microsoft.com/en-au/dynamics365/supply-chain/pim/product-lifecycle)
- [Dynamics product data entities](https://learn.microsoft.com/en-us/dynamics365/supply-chain/pim/data-entities)

### 4.5 Oracle Fusion Cloud SCM

Oracle supports several item-number generation methods at the Item Class level:

- inherited from the parent class;
- rule-generated;
- sequence-generated; and
- user-defined.

A sequence-generated number can have a starting number, increment, and optional
prefix or suffix. Changing the generation method does not rewrite existing item
numbers.

Oracle separates internal item identity from a particularly comprehensive set
of relationships:

- manufacturer item and manufacturer part number;
- supplier item and supplier part number;
- customer item;
- source-system item;
- old item number or other cross-reference;
- GTIN;
- substitute, superseded, or other related items; and
- item class, lifecycle phase, lot control, and serial control.

Trading-partner item relationships can be many-to-many, ranked, status-aware,
and effective-dated. Related-item relationships can also be directional,
ranked, effective-dated, and planning-enabled.

Oracle provides the clearest direct example of the recommended architecture:
one internal item with multiple typed relationships to identifiers used by
other organizations and systems.

Sources:

- [Oracle number generation methods](https://docs.oracle.com/en/cloud/saas/supply-chain-and-manufacturing/26b/fapim/number-generation-methods.html)
- [Oracle item relationships](https://docs.oracle.com/en/cloud/saas/supply-chain-and-manufacturing/26a/fapim/overview-of-item-relationships.html)
- [Oracle trading-partner item relationships](https://docs.oracle.com/en/cloud/saas/supply-chain-and-manufacturing/26c/fapim/trading-partner-item-relationships.html)
- [Oracle related-item relationships](https://docs.oracle.com/en/cloud/saas/supply-chain-and-manufacturing/26c/fapim/related-items-relationships.html)
- [Oracle item lifecycle phases](https://docs.oracle.com/en/cloud/saas/supply-chain-and-manufacturing/25d/faicf/item-lifecycle-phases.html)
- [Oracle inventory item attributes](https://docs.oracle.com/en/cloud/saas/supply-chain-and-manufacturing/26b/faims/inventory-item-attributes.html)

### 4.6 MRPeasy

MRPeasy uses a required, unique **Part Number** to identify an item. MRPeasy can
generate the number automatically, and it allows a controlled change to the
number. Part Description, Product Group, UOM, procurement/manufacturing
settings, vendor part numbers, and BOMs remain separate.

MRPeasy's CSV workflows match and update items by Part Number rather than by
description. It also separates item identity from stock lots and uses archived
or hidden records to preserve transaction history.

This demonstrates that the unique-code pattern is not merely an enterprise ERP
complication. It is also normal in comparatively lightweight manufacturing
software.

Sources:

- [MRPeasy Item Details](https://www.mrpeasy.com/resources/user-manual/stock/items/details/)
- [MRPeasy Items](https://www.mrpeasy.com/resources/user-manual/stock/items/)
- [MRPeasy CSV import](https://www.mrpeasy.com/resources/user-manual/one/)
- [MRPeasy Stock Lots](https://www.mrpeasy.com/resources/user-manual/stock/lots/)

### 4.7 Katana

Katana models a material and its concrete variants. Each variant can have its
own Variant Code/SKU, barcode, supplier information, and stock level. Imports
match materials by Variant Code/SKU and skip duplicates rather than relying on
the material name.

Katana also distinguishes:

- material name from Variant Code/SKU;
- a material family from each stockable variant;
- internal barcode from supplier item code and batch barcode;
- active material from archived material; and
- planned recipe ingredients from quantities actually used on a manufacturing
  order.

Archived materials remain connected to historical records. Names and SKUs of
archived records remain relevant to duplicate prevention and history.

Katana therefore reinforces two conclusions relevant to Task 20: identity
belongs at the exact stockable material variant, and planned versus executed
production information must remain separate.

Sources:

- [Katana materials](https://support.katanamrp.com/en/articles/5967034-what-is-a-material)
- [Katana variants](https://support.katanamrp.com/en/articles/5967049-what-is-a-variant)
- [Katana material and variant import](https://support.katanamrp.com/en/articles/5967027-how-to-import-materials-and-variants-via-template)
- [Katana barcode types](https://support.katanamrp.com/en/articles/5966985-different-types-of-barcodes)
- [Katana archiving](https://support.katanamrp.com/en/articles/10304438-archiving-a-product-material-or-service)
- [Katana manufacturing orders](https://support.katanamrp.com/en/articles/5914365-how-to-create-a-manufacturing-order-mo)

### 4.8 GS1 Standards

GS1's Global Trade Item Number identifies a trade item: something that may be
priced, ordered, or invoiced. It is an important external product identifier,
but it is not a replacement for an organization's own internal material master
identity.

GS1 also clearly separates identity levels:

- GTIN identifies the trade item;
- Application Identifier 10 identifies a batch or lot;
- Application Identifier 21 identifies a serial number; and
- other Application Identifiers carry dates, quantities, and related data.

One barcode can encode several of these elements, but the application should
parse and store them as separate values. It should not treat the complete
scanner string as the only representation of material, lot, and serial data.

The relevant lesson is that trade-item identity, internal material identity,
batch identity, and instance identity are different things even when a barcode
physically carries several of them.

Sources:

- [GS1 GTIN](https://www.gs1.org/standards/id-keys/gtin)
- [GS1 Application Identifiers](https://www.gs1.org/gs1-application-identifiers)
- [GS1 General Specifications](https://ref.gs1.org/standards/genspecs/17.1.0/)
- [GS1 Global Traceability Standard](https://www.gs1.org/standards/gs1-global-traceability-standard/current-standard)

## 5. Common Architecture Pattern

Across the reviewed systems, the durable pattern has five layers.

### 5.1 Internal Master Identity

The internal identity exists solely to establish that all references point to
the same record. It should not depend on spelling, category, supplier, producer,
or current application.

For this project, that role should be filled by an immutable `material_id`,
preferably a UUID generated by the authoritative material-master system.

### 5.2 Human-Usable Business Code

A short business code makes imports, support, investigation, and human review
more manageable than exposing a UUID. The code should be globally unique in the
material domain and permanent once allocated.

Recommended example:

```text
MAT-000001
MAT-000002
MAT-000003
```

The constant `MAT` prefix merely identifies the namespace. The numeric portion
has no business meaning.

The code should not include:

- category;
- producer or manufacturer;
- grade;
- supplier;
- year of creation;
- plant or process;
- UOM; or
- active/inactive status.

Those facts may change without changing which material the record represents.
Embedding them would make the code misleading or force unnecessary renumbering.

### 5.3 Descriptive Master Data

Editable descriptive fields explain what the material is and how users should
find it. They are not identifiers.

The minimum relevant fields are:

- canonical/current full name;
- process-specific display name;
- category;
- producer/manufacturer;
- brand family;
- grade code;
- base UOM;
- lifecycle status; and
- notes or description.

The current `TechnologyCardDisplayName` is therefore a process-specific label,
not a competing material identity. Other processes may have their own familiar
label while sharing the same `material_id` and `material_code`.

### 5.4 Typed External Identifiers

External identifiers should be repeatable records carrying their type and
scope. Examples are:

- manufacturer plus manufacturer part number;
- supplier plus supplier part number;
- GTIN plus packaging/UOM context;
- barcode plus barcode type;
- ERPNext Item Code;
- Odoo database/model/record ID;
- Odoo External ID;
- old Shift Manager catalogue name;
- historical costing-file code; and
- source-system record ID.

The issuer or source is part of the meaning. The raw text `G300`, for example,
does not become globally unique merely because one supplier or producer uses
it.

### 5.5 Transaction And Traceability Identity

Production and inventory events add identities that must remain separate from
the material master:

- purchase or production lot/batch;
- serial number where required;
- inventory location;
- stock movement;
- order/card;
- planned recipe snapshot; and
- executed recipe snapshot.

A batch is a batch **of** a material. It is not a new material master record.

## 6. Recommended Material-Code Policy

### 6.1 Allocation

The authoritative material-master system should allocate the next code from one
central sequence in the same transaction that creates the material.

Conceptually:

```text
next code = MAT- + zero-padded next sequence value
```

The sequence must prevent concurrent duplicate allocation. Codes should be
stored as text because prefixes and leading zeroes are part of the business
representation.

During the interim CSV period, the codes must be allocated once and retained in
the maintained source data. The extrusion terminal must not assign a new code
each time the same CSV row is uploaded.

### 6.2 Immutability And Reuse

Once issued, a material code should:

- never be reassigned to another material;
- not change because of a spelling correction;
- not change because of a category reorganization;
- not change because a different UI label is preferred;
- not change because the material is inactive; and
- remain resolvable from historical recipes and transactions.

If a code is entered incorrectly during initial master-data creation, correction
should be a rare governed operation with retained aliases or audit history. It
should not be an ordinary edit.

### 6.3 New Code Versus Updated Record

A new code is needed when the business must track two things separately for at
least one of these reasons:

- inventory balance;
- cost or valuation;
- recipe compatibility;
- purchasing or replenishment;
- quality specification;
- regulatory or safety status;
- traceability; or
- approved substitution.

Practical examples:

- Correcting whitespace or spelling: same code.
- Changing the terminal display name: same code.
- Moving a material to another catalogue category: same code.
- Receiving another batch of the same accepted material: same material code,
  different batch/lot.
- Buying the same accepted material from another supplier: potentially the same
  material code with another supplier identifier.
- A different producer/grade that must be selected separately in recipes or
  tracked separately in inventory: different code.
- The same underlying material in another package size: the same material may
  remain appropriate if stock is pooled in kilograms and packaging is only a
  purchase/UOM relationship; use a different code if the packages are stocked,
  valued, approved, or consumed as distinct items.

The operative question is:

> Must these two definitions ever have separate stock, consumption, cost,
> approval, quality, or traceability?

If yes, they need separate material identities.

## 7. Provisional Data Contract

The combined design should consider the following source-neutral structure.
This is a conceptual contract, not an approved SQL schema.

### 7.1 Material Master

```text
material_id             immutable machine identifier
material_code           permanent unique business code
canonical_name          current full material name
category_id             controlled material classification
producer_id             optional producer/manufacturer reference
brand_family            optional brand-family text/reference
grade_code              optional producer/grade designation
base_uom_code           canonical inventory and consumption UOM
lifecycle_status        active, inactive, or obsolete
notes                   optional descriptive information
created_at              creation timestamp
updated_at              last master-data update timestamp
row_version             optimistic concurrency/version value
```

The actual application may use a database-native integer primary key in
addition to `material_id`. That is an implementation concern; all cross-system
communication should use the stable source-neutral identity and code.

### 7.2 Process-Specific Labels

If several applications or processes need different familiar names, labels can
be represented separately:

```text
material_id
context                  extrusion_terminal, solvents, costing, etc.
label
language                 optional
is_default
```

Task 20's `TechnologyCardDisplayName` is the extrusion-terminal label.

### 7.3 External Identifiers

```text
material_id
identifier_type         supplier_part, manufacturer_part, gtin, barcode,
                        erpnext_item, odoo_product, legacy_name, etc.
identifier_value
issuer_or_source         supplier, manufacturer, system, database/tenant
uom_or_packaging         optional GTIN/barcode context
valid_from               optional
valid_until              optional
is_primary               optional within its type/scope
```

Uniqueness must be enforced at the correct scope. A manufacturer part number
is normally meaningful together with its manufacturer. A supplier code is
normally meaningful together with its supplier. An external application ID is
meaningful together with the source system, tenant/database, and model.

### 7.4 Relationships

Future material relationships should not be represented as aliases. A
substitute is another material, not another name for the same material.

Possible future relationship data is:

```text
from_material_id
to_material_id
relationship_type       substitute, superseded, equivalent, related
direction
priority
effective_from
effective_until
approval_status
scope_or_process
conversion_factor       only when explicitly defined
```

Task 20 does not need a substitution-management UI now. The important point is
not to misuse material aliases or shared names as implicit substitution rules.

## 8. Consequences For Task 20

### 8.1 `FullMaterialName` Should Stop Being Identity

Task 20 currently defines:

```text
FullMaterialName = canonical catalogue identity and durable full-name snapshot
```

The proposed corrected meaning is:

```text
MaterialCode                  canonical business identifier
MaterialId                    immutable machine identifier
FullMaterialName              current descriptive full name and recipe snapshot
TechnologyCardDisplayName     extrusion-operator display label and snapshot
```

`FullMaterialName` remains useful and should still be snapshotted. The change is
that renaming it no longer changes material identity.

### 8.2 Executed-Recipe Storage

A catalogue-selected executed row should retain both identity and historical
presentation:

```text
material_id
material_code_snapshot
category_snapshot
full_material_name_snapshot
terminal_display_name_snapshot
percentage
selection_source
```

The permanent reference supports later inventory consumption. The snapshots
preserve what production saw and selected even after the current material
master changes.

Free-text exceptions remain valid operational records but have no invented
material identity. They must be explicitly mapped before a future inventory
posting.

### 8.3 Planned Recipes That Currently Contain Names

The current Shift Manager order import contains material/category text rather
than permanent material codes. During a transitional period, the application
can preserve the source text and separately attempt an exact catalogue
resolution:

1. Normalize only agreed harmless whitespace and casing rules.
2. Resolve the planned value only when it matches exactly one known catalogue
   material.
3. Attach the resolved material identity without rewriting the source text.
4. Leave unmatched or ambiguous planned values explicitly unresolved.
5. Never make an automatic fuzzy match.

Eventually the Shift Manager workbook should retain the material code behind
each recipe selection. The code need not be prominent in the manager's normal
UI, but it should accompany the recipe across the integration boundary.

### 8.4 Re-Import Comparison

Once material identity is available, planned-versus-executed recipe comparison
should prefer the permanent material identity:

- matching `material_id` values mean the material is the same even if a name
  changed;
- different identities mean different materials even if display names happen
  to match; and
- exact normalized text comparison remains only a fallback when one or both
  planned values have not yet been resolved to the material master.

The existing rule that Batch/Lot does not participate in recipe compatibility
remains correct.

### 8.5 Catalogue Replacement

Task 20 currently describes an atomic replacement of the active catalogue.
Stable material identities require a refinement:

- the **active catalogue projection** may still be replaced atomically;
- material master records should be upserted by `MaterialCode`/`MaterialId`;
- a material missing from a new complete catalogue should become inactive when
  the source contract says absence means inactivation;
- referenced material records should not be deleted; and
- executed-recipe snapshots must never be rewritten by a catalogue refresh.

This preserves the simple full-file upload workflow without destroying durable
identity.

## 9. CSV Now And API Later

The durable contract should remain independent of its transport.

### 9.1 Provisional CSV Shape

A future combined design could revise the seven-column Task 20 catalogue into a
contract similar to:

```text
MaterialCode,
Category,
Producer,
BrandFamily,
GradeCode,
FullMaterialName,
TechnologyCardDisplayName,
BaseUOM,
Status,
Notes
```

Whether `MaterialId` also appears in the human-maintained CSV depends on which
system initially issues it. It may be kept as hidden/source-managed data while
`MaterialCode` is the visible stable import key.

The important rules are:

- updates match by code or authoritative ID, never by name;
- one code cannot describe two materials;
- names can change without creating duplicate materials;
- a missing code is a creation/error decision, not an invitation to name-match;
- a full-file upload is validated before any active-set change;
- import metadata and warnings remain available; and
- production snapshots are not rewritten by an import.

### 9.2 Authority Transition

Before the inventory application exists, a controlled CSV/workbook source may
be the temporary authority. It must assign the initial codes once and retain
them on every later export.

When the inventory application is created:

1. Import/adopt the same material IDs and codes rather than renumbering them.
2. Make the inventory application's material master authoritative.
3. Publish the material contract through a versioned API or another explicit
   synchronization boundary.
4. Let the extrusion terminal maintain a local read-optimized catalogue copy.
5. Resolve synchronization by source ID/code, not by material name.
6. Use source timestamps/versioning and idempotent upserts.
7. Mark missing/deactivated materials inactive locally while retaining history.

Under that model, moving from CSV to API changes where the data comes from and
how it is transported. It does not change the identity stored on planned or
executed recipes.

## 10. Alternatives Considered

### 10.1 Continue Using `FullMaterialName`

Advantages:

- no new field; and
- superficially simple with the present 26-row catalogue.

Problems:

- renames break identity;
- spelling and whitespace corrections resemble new materials;
- different applications cannot safely use different display names;
- duplicate or translated names become ambiguous;
- supplier/producer changes are difficult to interpret;
- later inventory integration depends on fragile string matching; and
- historical recipe reconciliation becomes unnecessarily difficult.

Conclusion: reject as the permanent model.

### 10.2 Use Only A Human Business Code

Advantages:

- simple CSV and database representation;
- easy for people to read and support; and
- consistent with the visible Item/Part Number model in many ERPs.

Problems:

- a future rename or correction becomes a key migration;
- integrating several systems requires deciding which system's mutable code is
  authoritative; and
- it is less robust for source-system mapping and code history.

Conclusion: acceptable for a very small standalone catalogue, but weaker than
using an immutable internal ID plus the human code.

### 10.3 Use Immutable ID Plus Permanent Business Code

Advantages:

- stable joins and API references;
- human-readable imports and support;
- names and process labels can change safely;
- external ERP identifiers can be mapped without becoming authority;
- CSV-to-API transition does not change identity; and
- historical recipe records remain understandable.

Cost:

- one additional identity field and explicit alias handling.

Conclusion: recommended. The additional complexity is small and directly
addresses a known cross-application requirement rather than speculative future
functionality.

## 11. Design Principles To Carry Into The Combined Recommendation

The following principles have strong support from all reviewed systems:

1. **Never use a display name as the automatic cross-system identity.**
2. **Assign identity at the exact stockable/consumable material level.** A
   family or template can group materials but cannot replace the concrete item.
3. **Keep identifiers typed and scoped.** Supplier code, manufacturer part
   number, barcode, GTIN, legacy name, and source-system ID have different
   meanings.
4. **Keep material, batch, and serial identity separate.**
5. **Use deactivation rather than hard deletion or code reuse.**
6. **Represent substitution explicitly.** A substitute is another material,
   not an alias for the same record.
7. **Snapshot human-readable recipe data.** Historical production should remain
   understandable after master-data edits.
8. **Link snapshots to stable identity where known.** This enables inventory,
   costing, comparison, and reconciliation.
9. **Make imports idempotent.** Repeated delivery of the same source state must
   update, not duplicate, materials.
10. **Change transport without changing the domain contract.** CSV and API are
    delivery mechanisms for the same material master.

## 12. Matters To Reconcile With The Other Project's Report

The combined design should explicitly resolve these points after the previous
research is supplied:

1. **Master scope:** whether one shared master covers raw materials only or all
   inventory items, packaging, WIP, and finished goods.
2. **Code namespace:** whether the permanent public code should use `MAT`,
   `ITEM`, a purely numeric format, or an existing company-wide convention.
3. **Initial authority:** which system allocates the first IDs/codes before the
   inventory application exists.
4. **Authority transfer:** how the inventory application adopts the initial
   catalogue without renumbering or creating parallel identities.
5. **Granularity policy:** particularly whether producer-specific grades and
   packaging variants require separate material codes in the company's actual
   stock and costing practice.
6. **Category governance:** whether categories are global or process-specific,
   and whether they require stable category codes of their own.
7. **UOM governance:** the canonical UOM for each material and which explicit
   conversions are allowed.
8. **Process labels:** whether multiple applications need formally stored label
   aliases or whether only one canonical name plus one terminal label is
   currently sufficient.
9. **Legacy mapping:** how previous Shift Manager names, historical actual-
   material text, and identifiers from costing or other files map to the new
   master.
10. **Source identifiers:** whether the previous project already chose UUID,
    ULID, sequence, ERP-originated ID, or another canonical machine identifier.
11. **Change governance:** who may create, rename, deactivate, merge, or
    supersede a material and what audit record is required.
12. **Synchronization contract:** which fields the inventory application will
    own and whether terminals may ever add local catalogue data beyond explicit
    free-text production exceptions.

These are the meaningful decisions for the combined design. They should be
resolved once, in the future material-master specification, instead of being
answered independently by Task 20, the inventory application, and each
workbook.

## 13. Provisional Recommendation For The Combined Review

Unless the previous work identifies a stronger existing company-wide standard,
the combined recommendation should begin from this model:

```text
One material master
    -> immutable machine material_id
    -> permanent non-semantic material_code
    -> editable canonical name and process labels
    -> category, producer, grade, UOM, lifecycle
    -> typed external identifiers and aliases
    -> separate lots/batches and serials
    -> separate substitution/supersession relationships
    -> snapshots on production recipes and transactions
```

For Task 20 specifically, the immediate specification correction would be to
add stable material identity to the catalogue and executed-recipe snapshot,
stop describing `FullMaterialName` as identity, and preserve the deliberate
free-text exception as an explicit unresolved material rather than manufacturing
a false code.

No Task 20 or implementation-plan change should be made from this report alone.
The next step is to compare it with the earlier project report, resolve any
different assumptions, and write one combined recommendation for approval.
