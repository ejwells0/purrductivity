# app.py
# rumps.App subclass — menu bar icon and menu items.
# Source: Phase 1 Research — Pattern 2
#
# RULE: No ctk.* or tk.* calls here. All UI goes through enqueue().
import rumps

from ui.tk_host import enqueue


class PurrductivityApp(rumps.App):
    def __init__(self):
        super().__init__(
            name="Purrductivity",
            title="",
            icon="assets/cat_icon.png",
            quit_button="Quit Purrductivity",
            template=True,
        )
        self.menu = ["Open", None]   # None = menu separator

    @rumps.clicked("Open")
    def open_panel_clicked(self, _sender):
        enqueue("show")
