from pages.base_page import BasePage
from pages.setup_workflow import SetupWorkflow


class SetupPage(BasePage):
    def __init__(self, parent, app):
        super().__init__(
            parent,
            app,
            "Setup Mode",
            "Calibrate cameras, select circles, save expected pin holes, and choose QR reading.",
        )

        self.log.grid_remove()
        self.body.rowconfigure(0, weight=1)
        self.body.rowconfigure(1, weight=0)

        self.workflow = SetupWorkflow(self.body)
        self.workflow.grid(row=0, column=0, sticky="nsew")

    def refresh(self):
        self.workflow.refresh()
