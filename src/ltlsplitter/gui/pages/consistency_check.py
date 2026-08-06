from ltlsplitter.gui.pages.base import WizardPage


class ConsistencyCheckPage(WizardPage):
    title = "4. Consistency & Realizability Check"
    description = (
        "Verify the requirement set is satisfiable and realizable before generating monitors. "
        "Conflicting requirements are reported here rather than failing silently downstream."
    )
