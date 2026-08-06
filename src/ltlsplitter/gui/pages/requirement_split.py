from ltlsplitter.gui.pages.base import WizardPage


class RequirementSplitPage(WizardPage):
    title = "1. Requirement Splitting"
    description = (
        "Enter a natural-language requirement. An LLM splits it into sub-requirements "
        "(e.g. r1.1 ∧ r1.2 ⇒ R1) for review before they're formalized."
    )
