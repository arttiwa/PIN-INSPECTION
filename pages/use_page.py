from pages.base_page import BasePage
from pages.use_workflow import UseWorkflow


class UsePage(BasePage):
    def __init__(self, parent, app):
        super().__init__(
            parent,
            app,
            "Use Mode",
            "Run inspection with the saved setup and write result images to inspection_output.",
        )
        self.log.grid_remove()
        self.body.rowconfigure(0, weight=1)
        self.body.rowconfigure(1, weight=0)

        self.workflow = UseWorkflow(self.body)
        self.workflow.grid(row=0, column=0, sticky="nsew")

    def refresh(self):
        self.workflow.refresh()
