# Shift-Manager Verification Questions

Purpose: confirm whether the forward-looking workbook conventions are usable for
tracked production orders starting in July 2026.

Use together with `naming-convention-preview.html`.

## Sales Price

1. Do shift managers approve using column `O` as one numeric value that always
   means EUR/kg, excluding VAT, for forward-looking tracked production orders?

## Naming Conventions

2. Do shift managers approve the proposed naming conventions, and are they easy
   enough to use consistently?

```text
Extrusion raw materials/additives:
[Material/Additive Category] [Producer or Brand] [Full Commercial Grade/Code]

Recipe cells:
Material Name | %

Printing ink station fields:
Color Identity | Anilox lines/cm

Polypropylene film:
[Film Type] [Product Series] [Thickness] [Width mm]
```

3. What is the preferred way to help shift managers use the new names and
   formats?

Options to discuss:

- Month-start raw-material/additive inventory list.
- Workbook dropdowns.
- Separate reference sheet or document.
- Workbook verification macro.
- App-side validation when the workbook is uploaded.

4. Are equivalent colors from different ink suppliers/manufacturers
   interchangeable in production, so manufacturer can be excluded from the
   workbook-facing color identity?

## Extrusion Recipe Structure

5. Do real extrusion recipes fit within four base polymer slots `AM:AP` and
   three additive/filler slots `AQ:AS`?

6. Is the costing interpretation correct: base polymers in `AM:AP` sum to
   `100%`, and additives/fillers in `AQ:AS` are percentages over the base blend
   rather than part of the base `100%`?

7. Do shift managers need a reference table or calculator to convert current
   shorthand such as ratios, bag counts, or `20% KJ` into percentages?

## Solvents

8. How is solvent usage currently captured, if at all?

9. If solvent usage is not captured per order/card, should solvent cost be
   allocated monthly?
