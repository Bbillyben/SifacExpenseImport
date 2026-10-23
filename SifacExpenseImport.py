from django.utils.translation import gettext_lazy as _
import tablib
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from plugin import LabManagerPlugin
from plugin.mixins import ImportMixin


class SifacExpenseImport(ImportMixin, LabManagerPlugin):
    NAME = 'SifacExpenseImport'
    SLUG = 'sifacexpenseimport'
    TITLE = _('Sifac Import')
    AUTHOR = _('LabsManager contributors/Bbillyben')
    DESCRIPTION = _('A plugin to import expense from sifac')
    VERSION = '0.0.0'
    
    OUTPUT_HEADERS = (
            "Expense Id",
            "Description",
            "type",
            "Ref",
            "Amount",
            "date",
        )

    import_method = [
        {
            "id": "expenses_inserm",
            "label": "Import expenses Inserm",
            "resource": "ExpenseResource",
            "handler": "transform_expenses_inserm",
            "columns": {
                "Poste": [],
                "Document d'achat": [],
                "Fournisseur": ["Fournisseur/Division cédante"],
                "Désignation": [],
                "Valeur nette": ["Val. nette commande"],
                "Elément d'OTP": [],
                "Fonds": [],
                "Date du document": [],
            },
        },
        {
            "id": "expenses_ul",
            "label": "Import expenses Université de Lille",
            "resource": "ExpenseResource",
            "handler": "transform_expenses_ul",
            "columns": {
                "Poste": [],
                "Document d'achat": ["Doc achat"],
                "Fournisseur": ["Fournisseur/Division fourn."],
                "Désignation": [],
                "Valeur nette": ["Valeur nette de cde", "Val. nette"],
                "Elément d'OTP": ["      Elt d'OTP"],
                "Date du document": ["Date doc."],
            },
        },
    ]
    
    def prepare_dataset(self, dataset, current_import_methode, option_data=None):
        if current_import_methode["id"] == "expenses_ul":
            return self._prepare_ul_dataset(dataset, current_import_methode)

        return dataset


    def _prepare_ul_dataset(self, dataset, current_import_methode):
        """
        Prepare UL exports:
        - Detect the header row, even when preceded by an export date.
        - Support files with headers already on the first row.
        - Remove fully empty data rows.
        - Preserve original column names for ImportMixin normalization.
        """

        columns = current_import_methode["columns"]

        # Build the set of accepted names for each canonical column.
        expected = {
            canonical: {
                self._header(name)
                for name in (canonical, *aliases)
            }
            for canonical, aliases in columns.items()
        }

        # Include current headers as the first candidate row.
        candidates = []

        if dataset.headers:
            candidates.append(list(dataset.headers))

        candidates.extend(list(row) for row in dataset)

        # Find the row containing all required columns.
        header_index = None

        for index, row in enumerate(candidates):
            normalized = [self._header(value) for value in row]

            if all(
                any(name in normalized for name in aliases)
                for aliases in expected.values()
            ):
                header_index = index
                break

        # Let ImportMixin report missing columns if none match.
        if header_index is None:
            return dataset

        headers = candidates[header_index]
        data_rows = candidates[header_index + 1:]

        # Remove fully empty rows.
        data_rows = [
            row for row in data_rows
            if any(value is not None and str(value).strip() for value in row)
        ]

        return tablib.Dataset(*data_rows, headers=headers)
    
    def transform_expenses_inserm(self, dataset, current_import_methode):
        output = tablib.Dataset(headers=self.OUTPUT_HEADERS)

        for row_number, row in enumerate(dataset.dict, start=2):
            ref_raw = str(row["Elément d'OTP"] or "").strip()
            fonds = str(row["Fonds"] or "").strip()

            # If empty => error
            if len(ref_raw) < 2 and not fonds.startswith("SE"):
                raise ValueError(
                    f"Inserm import - row {row_number}: "
                    f"Missing or invalid OTP reference: {ref_raw!r} "
                    f"(Fonds: {fonds!r})"
                )

            try:
                expense_date = self._parse_date(row["Date du document"])
                amount = self._parse_amount(row["Valeur nette"])

                expense_type = self._get_inserm_expense_type(fonds)
                ref = self._build_inserm_ref(ref_raw, fonds, expense_date)

                self._append_expense(
                    output,
                    row,
                    ref,
                    expense_type,
                    amount,
                    expense_date,
                )

            except ValueError as exc:
                raise ValueError(
                    f"Inserm import - row {row_number}: {exc}"
                ) from exc

        return output


    def transform_expenses_ul(self, dataset, current_import_methode):
        output = tablib.Dataset(headers=self.OUTPUT_HEADERS)

        for row_number, row in enumerate(dataset.dict, start=2):
            ref_raw = str(row["Elément d'OTP"] or "").strip()

            # UL has no Fonds column.
            # Ignore rows without a usable OTP reference.
            if len(ref_raw) < 2:
                continue

            try:
                expense_date = self._parse_date(row["Date du document"])
                amount = self._parse_amount(row["Valeur nette"])

                expense_type = self._get_ul_expense_type()
                ref = self._build_ul_ref(ref_raw)

                self._append_expense(
                    output,
                    row,
                    ref,
                    expense_type,
                    amount,
                    expense_date,
                )

            except ValueError as exc:
                raise ValueError(
                    f"UL import - row {row_number}: {exc}"
                ) from exc

        return output


    def _build_expenses(self, dataset, source):
        # Les transformations communes seront développées ici.
        return dataset
    
    
    @staticmethod
    def _build_inserm_ref(ref_raw, fonds, expense_date):
        ref = str(ref_raw or "").strip()
        fonds = str(fonds or "").strip()

        if fonds.startswith("SE") and not ref:
            return f"INSERM_DOT_{expense_date.year}"

        if "LIL" in ref:
            position = ref.index("LIL")
            return ref[:position + len("LIL")]

        if "EU1190" in ref:
            position = ref.index("EU1190")
            return ref[:position]

        raise ValueError(
            f"Unrecognized Inserm financial reference: {ref!r} "
            f"(Fonds: {fonds!r})"
        )
    @staticmethod
    def _build_ul_ref(ref_raw):
        return str(ref_raw or "").strip()
    
    @staticmethod
    def _get_ul_expense_type():
        return "FCT"
    
    @staticmethod
    def _get_inserm_expense_type(fonds):
        fonds = str(fonds or "").strip()

        if "FONC" in fonds:
            return "FCT"
        elif "MISS" in fonds:
            return "MISSION"
        elif "SE_DIV" in fonds:
            return "FCT"
        elif "PRESTE" in fonds:
            return "PRESTA"
        elif "RPF_INV_E" in fonds:
            return "EQUIP"

        raise ValueError(
            f"Unrecognized Inserm expense type for Fonds: {fonds!r}"
        )
    
    
    @staticmethod
    def _parse_amount(value):
        if value is None or str(value).strip() == "":
            raise ValueError("Empty expense amount")

        text = str(value).strip().replace(" ", "").replace("\u00a0", "").replace("\u202f", "")

        if "," in text:
            text = text.replace(".", "").replace(",", ".")

        try:
            amount = Decimal(text)
        except InvalidOperation as exc:
            raise ValueError(f"Invalid expense amount: {value!r}") from exc

        if not amount.is_finite():
            raise ValueError(f"Non-finite expense amount: {value!r}")

        return amount

    @staticmethod
    def _parse_date(value):
        if isinstance(value, datetime):
            return value.date()

        if isinstance(value, date):
            return value

        if value is None or not str(value).strip():
            raise ValueError("Empty expense date")

        text = str(value).strip()

        for date_format in ("%d/%m/%Y", "%d.%m.%Y", "%Y-%m-%d"):
            try:
                return datetime.strptime(text, date_format).date()
            except ValueError:
                continue

        raise ValueError(f"Invalid expense date: {value!r}")
    
    
    @staticmethod
    def _append_expense(output, row, ref, expense_type, amount, expense_date):
        document = str(row["Document d'achat"] or "").strip()
        poste = str(row["Poste"] or "").strip()
        fournisseur = str(row["Fournisseur"] or "").strip()
        designation = str(row["Désignation"] or "").strip()

        if not document or not poste:
            raise ValueError("Missing purchase document or position")

        expense_id = f"{document}-{poste}-{ref}"
        description = f"{fournisseur}//{designation}"

        output.append((
            expense_id,
            description,
            expense_type,
            ref,
            amount,
            expense_date,
        ))