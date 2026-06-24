"""
Credential list window with search and management
"""
import ttkbootstrap as ttk
from ttkbootstrap.constants import *
from tkinter import messagebox
from typing import Dict
from models.credential import Credential
from ui.credential_dialog import CredentialDialog


class CredentialListWindow:
    """Window for listing and managing credentials."""

    def __init__(self, parent, credentials: Dict[str, Credential],
                 on_update=None, clipboard_manager=None):
        """
        Initialize credential list window.

        Args:
            parent: Parent window
            credentials: Dictionary of credentials
            on_update: Callback(action, credential, old_service) for updates
            clipboard_manager: ClipboardManager instance
        """
        self.parent = parent
        self.credentials = credentials
        self.on_update = on_update
        self.clipboard_manager = clipboard_manager

        # Create window
        self.window = ttk.Toplevel(parent)
        self.window.title("Stored Credentials")
        self.window.geometry("800x500")
        self.window.transient(parent)

        # Center window
        self.window.update_idletasks()
        x = (self.window.winfo_screenwidth() // 2) - (800 // 2)
        y = (self.window.winfo_screenheight() // 2) - (500 // 2)
        self.window.geometry(f"800x500+{x}+{y}")

        self._create_widgets()
        self._populate_tree()

    def _create_widgets(self):
        """Create window widgets."""
        # Main frame
        main_frame = ttk.Frame(self.window, padding=15)
        main_frame.pack(fill=BOTH, expand=YES)

        # Title and search
        header_frame = ttk.Frame(main_frame)
        header_frame.pack(fill=X, pady=(0, 15))

        ttk.Label(
            header_frame,
            text="Stored Credentials",
            font=("Segoe UI", 16, "bold")
        ).pack(side=LEFT)

        search_frame = ttk.Frame(header_frame)
        search_frame.pack(side=RIGHT)

        ttk.Label(search_frame, text="Search:", font=("Segoe UI", 10)).pack(side=LEFT, padx=(0, 5))

        self.search_var = ttk.StringVar()
        self.search_var.trace('w', lambda *args: self._populate_tree())

        search_entry = ttk.Entry(
            search_frame,
            textvariable=self.search_var,
            width=30
        )
        search_entry.pack(side=LEFT)

        # Treeview frame
        tree_frame = ttk.Frame(main_frame)
        tree_frame.pack(fill=BOTH, expand=YES)

        # Create treeview
        columns = ("Service", "Username", "Website", "Password")
        self.tree = ttk.Treeview(
            tree_frame,
            columns=columns,
            show="headings",
            selectmode="browse",
            bootstyle="info"
        )

        # Configure columns
        self.tree.heading("Service", text="Service Name")
        self.tree.heading("Username", text="Username")
        self.tree.heading("Website", text="Website")
        self.tree.heading("Password", text="Password")

        self.tree.column("Service", width=220, anchor=W)
        self.tree.column("Username", width=200, anchor=W)
        self.tree.column("Website", width=180, anchor=W)
        self.tree.column("Password", width=120, anchor=CENTER)

        # Scrollbars
        vsb = ttk.Scrollbar(tree_frame, orient="vertical", command=self.tree.yview)
        hsb = ttk.Scrollbar(tree_frame, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)

        # Grid layout
        self.tree.grid(row=0, column=0, sticky=(N, S, E, W))
        vsb.grid(row=0, column=1, sticky=(N, S))
        hsb.grid(row=1, column=0, sticky=(E, W))

        tree_frame.rowconfigure(0, weight=1)
        tree_frame.columnconfigure(0, weight=1)

        # Row colors
        self.tree.tag_configure("evenrow", background="#000000")
        self.tree.tag_configure("oddrow", background="#000000")

        # Right-click menu
        self.context_menu = ttk.Menu(self.window, tearoff=0)
        self.context_menu.add_command(label="View", command=self._view_credential)
        self.context_menu.add_command(label="Edit", command=self._edit_credential)
        self.context_menu.add_separator()
        self.context_menu.add_command(label="Open Website", command=self._open_url)
        self.context_menu.add_separator()
        self.context_menu.add_command(label="Copy Service Name", command=self._copy_service)
        self.context_menu.add_command(label="Copy Username", command=self._copy_username)
        self.context_menu.add_command(label="Copy Password", command=self._copy_password)
        self.context_menu.add_separator()
        self.context_menu.add_command(label="Delete", command=self._delete_credential)

        self.tree.bind("<Button-3>", self._show_context_menu)
        self.tree.bind("<Double-Button-1>", self._on_double_click)
        self.tree.bind("<Button-1>", self._on_single_click)

        # Info and help labels
        info_frame = ttk.Frame(main_frame)
        info_frame.pack(fill=X, pady=(10, 0))

        self.info_label = ttk.Label(
            info_frame,
            text="",
            font=("Segoe UI", 9),
            bootstyle="secondary"
        )
        self.info_label.pack(side=LEFT)

        # Help text
        ttk.Label(
            info_frame,
            text="💡 Tip: Click password to copy • Double-click to view • Right-click for more options",
            font=("Segoe UI", 8),
            bootstyle="info"
        ).pack(side=RIGHT)

    def _populate_tree(self):
        """Populate treeview with credentials."""
        # Clear existing
        for item in self.tree.get_children():
            self.tree.delete(item)

        # Get search filter
        search_text = self.search_var.get().lower()

        # Filter and add credentials
        count = 0
        for service_name, credential in sorted(self.credentials.items()):
            # Apply search filter
            if search_text and (
                search_text not in service_name.lower()
                and search_text not in credential.username.lower()
                and search_text not in credential.website_url.lower()
            ):
                continue

            # Determine row color
            tag = "evenrow" if count % 2 == 0 else "oddrow"

            url_short = credential.website_url[:30] + ("…" if len(credential.website_url) > 30 else "") \
                if credential.website_url else ""

            # Insert row
            self.tree.insert(
                "",
                "end",
                iid=service_name,
                values=(service_name, credential.username, url_short, "••••••••"),
                tags=(tag,)
            )
            count += 1

        # Update info label
        total = len(self.credentials)
        if search_text:
            self.info_label.config(text=f"Showing {count} of {total} credentials")
        else:
            self.info_label.config(text=f"Total: {total} credentials")

        # Show message if empty
        if count == 0 and not search_text:
            messagebox.showinfo("No Credentials", "No credentials stored yet.")
            self.window.destroy()

    def _on_single_click(self, event):
        """Handle single click - quick copy password if clicked on password column."""
        region = self.tree.identify_region(event.x, event.y)
        if region == "cell":
            column = self.tree.identify_column(event.x)
            row_id = self.tree.identify_row(event.y)

            # Column #4 is Password column (Service, Username, Website, Password)
            if column == "#4" and row_id:
                # Quick copy password
                self.tree.selection_set(row_id)
                self._copy_password()

    def _on_double_click(self, event):
        """Handle double click - view credential details."""
        region = self.tree.identify_region(event.x, event.y)
        if region == "cell" or region == "tree":
            self._view_credential()

    def _show_context_menu(self, event):
        """Show context menu on right-click."""
        # Select row under cursor
        row_id = self.tree.identify_row(event.y)
        if row_id:
            self.tree.selection_set(row_id)
            self.context_menu.post(event.x_root, event.y_root)

    def _get_selected_credential(self):
        """Get currently selected credential."""
        selection = self.tree.selection()
        if not selection:
            return None
        service_name = selection[0]
        return self.credentials.get(service_name)

    def _view_credential(self):
        """View selected credential."""
        credential = self._get_selected_credential()
        if not credential:
            return

        CredentialDialog(
            self.window,
            mode=CredentialDialog.MODE_VIEW,
            credential=credential,
            clipboard_manager=self.clipboard_manager
        )

    def _edit_credential(self):
        """Edit selected credential."""
        credential = self._get_selected_credential()
        if not credential:
            return

        def on_save(new_credential, old_service):
            if self.on_update:
                self.on_update("edit", new_credential, old_service)
            # Refresh list
            self._populate_tree()

        CredentialDialog(
            self.window,
            mode=CredentialDialog.MODE_EDIT,
            credential=credential,
            existing_services=set(self.credentials.keys()),
            on_save=on_save,
            clipboard_manager=self.clipboard_manager
        )

    def _open_url(self):
        """Open credential website in browser."""
        credential = self._get_selected_credential()
        if not credential or not credential.website_url:
            messagebox.showinfo("No Website", "This credential has no website URL.")
            return
        import webbrowser
        url = credential.website_url
        if not url.startswith(('http://', 'https://')):
            url = 'https://' + url
        webbrowser.open(url)

    def _copy_service(self):
        """Copy service name to clipboard."""
        credential = self._get_selected_credential()
        if not credential:
            return

        if self.clipboard_manager:
            from ui.settings_dialog import SettingsManager
            settings = SettingsManager.load_settings()
            self.clipboard_manager.copy_with_autoclear(
                credential.service_name,
                settings['clipboard_clear_seconds']
            )
        else:
            self.window.clipboard_clear()
            self.window.clipboard_append(credential.service_name)

    def _copy_username(self):
        """Copy username to clipboard."""
        credential = self._get_selected_credential()
        if not credential:
            return

        if self.clipboard_manager:
            from ui.settings_dialog import SettingsManager
            settings = SettingsManager.load_settings()
            self.clipboard_manager.copy_with_autoclear(
                credential.username,
                settings['clipboard_clear_seconds']
            )
        else:
            self.window.clipboard_clear()
            self.window.clipboard_append(credential.username)

    def _copy_password(self):
        """Copy password to clipboard."""
        credential = self._get_selected_credential()
        if not credential:
            return

        if self.clipboard_manager:
            from ui.settings_dialog import SettingsManager
            settings = SettingsManager.load_settings()
            self.clipboard_manager.copy_with_autoclear(
                credential.password,
                settings['clipboard_clear_seconds']
            )
        else:
            self.window.clipboard_clear()
            self.window.clipboard_append(credential.password)

    def _delete_credential(self):
        """Delete selected credential."""
        credential = self._get_selected_credential()
        if not credential:
            return

        # Confirm deletion
        if not messagebox.askyesno(
            "Confirm Delete",
            f"Are you sure you want to delete credentials for '{credential.service_name}'?"
        ):
            return

        if self.on_update:
            self.on_update("delete", credential, None)

        # Refresh list
        self._populate_tree()


def show_credential_list(parent, credentials, on_update=None, clipboard_manager=None):
    """
    Show credential list window.

    Args:
        parent: Parent window
        credentials: Dictionary of credentials
        on_update: Callback(action, credential, old_service) for updates
        clipboard_manager: ClipboardManager instance
    """
    if not credentials:
        messagebox.showinfo("No Credentials", "No credentials stored yet.")
        return

    CredentialListWindow(parent, credentials, on_update, clipboard_manager)
