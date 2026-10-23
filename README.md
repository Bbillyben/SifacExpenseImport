# SifacExpenseImport

**SIFAC expense import plugin for LabsManager**

SifacExpenseImport is a plugin for [LabsManager](https://github.com/bbillyben) that imports financial expense data from institutional SIFAC exports.

It converts raw Excel exports into the standardized expense format used by LabsManager, replacing a previously required Excel/VBA transformation workflow.

The plugin currently supports two institutional sources:

- **Inserm**
- **Université de Lille (UL)**

Each source has its own import handler, allowing institution-specific processing while sharing common data transformation functions.

> **Status: Experimental**
>
> The plugin is under active development. Import rules should be validated against actual institutional exports before use with production data.

## Features

- Import expense data from SIFAC Excel exports.
- Separate import methods for Inserm and Université de Lille.
- Automatic detection of column names and aliases.
- Support for different Université de Lille export layouts.
- Automatic removal of empty rows in supported UL layouts.
- Conversion of financial references, dates and amounts.
- Expense classification based on institution-specific rules.
- Generation of unique expense identifiers.
- Integration with the LabsManager Import Hub.
- Import preview and validation through the existing Django Import-Export infrastructure.
- Explicit errors for invalid or unrecognized financial data.

## Requirements

- A compatible installation of LabsManager.
- The LabsManager `ImportMixin` infrastructure.
- Django Import-Export and Tablib, provided by the LabsManager backend.

No additional Python dependency is currently required by the plugin.

## Installation

Clone the repository into the LabsManager external plugins directory:

```
cd /home/labsmanager/data/plugins/
git clone https://github.com/bbillyben/SifacExpenseImport.git
```

Expected structure:

```
data/plugins/
└── SifacExpenseImport/
    ├── __init__.py
    └── SifacExpenseImport.py
```

Ensure that the plugin directory and files are accessible to the LabsManager backend.

Restart or reload the backend as required by your deployment, then enable **Sifac Import** from the LabsManager plugin administration interface.

Once enabled, the plugin should appear in the Import Hub.

## Supported import methods

| Import method | Institution | Handler |
|:---|:---|:---|
| `expenses_inserm` | Inserm | `transform_expenses_inserm()` |
| `expenses_ul` | Université de Lille | `transform_expenses_ul()` |

### Inserm source columns

| Canonical column | SIFAC export column |
|:---|:---|
| `Poste` | Poste |
| `Document d'achat` | Document d'achat |
| `Fournisseur` | Fournisseur/Division cédante |
| `Désignation` | Désignation |
| `Valeur nette` | Val. nette commande |
| `Elément d'OTP` | Elément d'OTP |
| `Fonds` | Fonds |
| `Date du document` | Date du document |

All eight columns are required.

### Université de Lille source columns

| Canonical column | SIFAC export column |
|:---|:---|
| `Poste` | Poste |
| `Document d'achat` | Document d'achat |
| `Fournisseur` | Fournisseur/Division fourn. |
| `Désignation` | Désignation |
| `Valeur nette` | Valeur nette de cde |
| `Elément d'OTP` | Elément d'OTP |
| `Date du document` | Date du document |

All seven columns are required.

Unlike Inserm exports, raw Université de Lille exports do not require a `Fonds` column.

### Université de Lille layout handling

The plugin supports:

1. Files where column headers appear on the first row.
2. Files containing an export date and additional rows before the actual column headers.

The `prepare_dataset()` hook identifies the header row using the declared column names and aliases, then removes fully empty data rows.

This preparation occurs before column eligibility checks and normalization.

## Data transformations

The plugin produces the following standardized columns:

| Output column | Transformation |
|:---|:---|
| `Expense Id` | Purchase document + position + financial reference |
| `Description` | Supplier + `//` + designation |
| `type` | Institution-specific expense classification |
| `Ref` | Normalized financial reference |
| `Amount` | Parsed decimal amount |
| `date` | Parsed expense date |

### Expense identifiers

Expense identifiers follow the format:

```
<Document d'achat>-<Poste>-<Ref>
```

Example:

```
45000123-10-ABC123LIL
```

### Expense classification — Inserm

The `Fonds` column determines the expense type.

Rules are evaluated in the following order:

| Pattern in `Fonds` | Expense type |
|:---|:---|
| `FONC` | `FCT` |
| `MISS` | `MISSION` |
| `SE_DIV` | `FCT` |
| `PRESTE` | `PRESTA` |
| `RPF_INV_E` | `EQUIP` |

Unrecognized classifications raise an explicit error.

### Expense classification — Université de Lille

For the current version, all accepted UL expenses are classified as:

```
FCT
```

This is a provisional rule that may be refined in future versions.

### Financial references — Inserm

Inserm financial references are derived from `Elément d'OTP` and, where applicable, `Fonds`.

| Condition | Result |
|:---|:---|
| `Fonds` starts with `SE` and OTP is empty | `INSERM_DOT_<year>` |
| OTP contains `LIL` | Keep the reference through `LIL`, inclusive |
| OTP contains `EU1190` | Keep the part before `EU1190` |
| No recognized rule | Raise an error |

For dotations, the year is extracted from the expense date.

Unknown references are not silently accepted.

### Financial references — Université de Lille

UL references are taken directly from `Elément d'OTP`, with surrounding whitespace removed.

No Inserm-specific transformation is applied.

### Dates and amounts

The plugin uses Python date conversion and `Decimal` for monetary amounts.

Supported date formats currently include:

- `DD/MM/YYYY`
- `DD.MM.YYYY`
- `YYYY-MM-DD`
- Python `date` and `datetime` objects

Amounts can be parsed from numeric values and common decimal representations using either commas or periods.

Invalid values raise an explicit error instead of being silently replaced.

## Import workflow

The plugin uses the existing LabsManager import infrastructure:

```
Institutional Excel export
          |
          v
     Import Hub
          |
          v
   prepare_dataset()
          |
          v
   check_eligibility()
          |
          v
   normalize_columns()
          |
          v
Institution-specific handler
          |
          v
  Standardized Dataset
          |
          v
     ExpenseResource
          |
          v
 Preview and validation
          |
          v
    Confirm import
```

The plugin performs data transformations only.

Database validation, import preview, duplicate handling and final persistence are managed by LabsManager and Django Import-Export.

## Error handling

The plugin is designed to prevent silent data corruption.

Errors are raised when:

- A required source column is missing.
- Column aliases are ambiguous.
- A financial reference is invalid or unrecognized.
- An Inserm expense type cannot be classified.
- A date cannot be parsed.
- An amount cannot be converted.
- A required purchase document or position is missing.

Invalid or incomplete imports should be corrected before confirmation.

## Development

The main implementation is located in:

```
SifacExpenseImport.py
```

The plugin extends:

```
from plugin import LabManagerPlugin
from plugin.mixins import ImportMixin

class SifacExpenseImport(ImportMixin, LabManagerPlugin):
    ...
```

The code is organized around:

- `prepare_dataset()` — source layout preparation.
- `transform_expenses_inserm()` — Inserm-specific processing.
- `transform_expenses_ul()` — Université de Lille-specific processing.
- `_build_inserm_ref()` / `_build_ul_ref()` — financial references.
- `_get_inserm_expense_type()` / `_get_ul_expense_type()` — expense classification.
- `_parse_amount()` / `_parse_date()` — common value conversions.
- `_append_expense()` — construction of standardized expense records.

Future institutional rules should preferably be implemented in their corresponding handlers rather than added to the shared import infrastructure.

## Limitations

- Only Inserm and Université de Lille exports are currently supported.
- UL expense classification currently uses the provisional `FCT` rule.
- The plugin does not connect directly to the SAP/SIFAC API.
- Imported data must be validated using the LabsManager preview before confirmation.
- Compatibility with all historical SIFAC export variants has not yet been established.

## Contributing

Contributions, bug reports and improvements are welcome.

When reporting an import issue, include the source institution, export layout, relevant column names and the error message.

Do not include confidential financial records, supplier information or personal data in public issues.

## Author

Developed by **Bbillyben** as an external plugin for LabsManager.

## License

License to be defined. See the repository for future licensing information.
