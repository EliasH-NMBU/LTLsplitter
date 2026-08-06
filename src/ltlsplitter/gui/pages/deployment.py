from ltlsplitter.gui.pages.base import WizardPage


class DeploymentPage(WizardPage):
    title = "6. Deployment & Live Visualization"
    description = (
        "Deploy the generated monitors against the live ROS2 system. "
        "Shows node activity, violations, and current state-space position in real time."
    )
