"""
Custom theme definitions for SecureVault
"""
import ttkbootstrap as ttk
from ttkbootstrap import Style


def apply_hacker_theme(root):
    """
    Apply Hacker Style theme: Deep black with neon green and electric purple.
    Creates a striking, futuristic cyberpunk aesthetic.
    """
    style = ttk.Style()

    # Cyberpunk color palette
    colors = {
        'bg': '#000000',           # Deep black background
        'fg': '#00ff41',           # Neon green text (Matrix green)
        'selectbg': '#7b00ff',     # Electric purple for selections
        'selectfg': '#00ff41',     # Neon green text on purple
        'border': '#00ff41',       # Neon green borders
        'inputbg': '#0a0a0a',      # Slightly lighter black for inputs
        'inputfg': '#00ff41',      # Neon green input text
        'button': '#7b00ff',       # Electric purple buttons
        'buttontext': '#00ff41',   # Neon green button text
        'accent': '#00ff41',       # Neon green accents
        'accent2': '#7b00ff',      # Electric purple accents
    }

    # Apply theme colors to all widgets
    style.configure('.',
        background=colors['bg'],
        foreground=colors['fg'],
        bordercolor=colors['border'],
        darkcolor=colors['bg'],
        lightcolor=colors['accent'],
        troughcolor=colors['inputbg'],
        selectbackground=colors['selectbg'],
        selectforeground=colors['selectfg'],
        insertcolor=colors['fg'],
        fieldbackground=colors['inputbg'],
        font=('Segoe UI', 10)
    )

    # Frame styles
    style.configure('TFrame', background=colors['bg'])
    style.configure('TLabelframe', background=colors['bg'], foreground=colors['fg'], bordercolor=colors['accent'])
    style.configure('TLabelframe.Label', background=colors['bg'], foreground=colors['accent'])

    # Label styles
    style.configure('TLabel', background=colors['bg'], foreground=colors['fg'])

    # Button styles
    style.configure('TButton',
        background=colors['button'],
        foreground=colors['buttontext'],
        bordercolor=colors['accent'],
        darkcolor=colors['button'],
        lightcolor=colors['accent2'],
        relief='flat',
        font=('Segoe UI', 10, 'bold')
    )

    style.map('TButton',
        background=[('active', colors['accent2']), ('pressed', colors['selectbg'])],
        foreground=[('active', colors['bg']), ('pressed', colors['buttontext'])],
        bordercolor=[('active', colors['accent'])]
    )

    # Entry styles
    style.configure('TEntry',
        fieldbackground=colors['inputbg'],
        foreground=colors['inputfg'],
        bordercolor=colors['accent'],
        insertcolor=colors['fg'],
        selectbackground=colors['selectbg'],
        selectforeground=colors['selectfg']
    )

    # Combobox styles
    style.configure('TCombobox',
        fieldbackground=colors['inputbg'],
        foreground=colors['inputfg'],
        background=colors['inputbg'],
        bordercolor=colors['accent'],
        arrowcolor=colors['accent'],
        selectbackground=colors['selectbg'],
        selectforeground=colors['selectfg']
    )

    # Treeview styles
    style.configure('Treeview',
        background=colors['inputbg'],
        foreground=colors['fg'],
        fieldbackground=colors['inputbg'],
        bordercolor=colors['accent'],
        selectbackground=colors['selectbg'],
        selectforeground=colors['selectfg']
    )

    style.configure('Treeview.Heading',
        background=colors['button'],
        foreground=colors['buttontext'],
        bordercolor=colors['accent'],
        relief='flat'
    )

    # Scrollbar styles
    style.configure('TScrollbar',
        background=colors['button'],
        troughcolor=colors['bg'],
        bordercolor=colors['accent'],
        arrowcolor=colors['accent']
    )

    # Text widget (via tkinter)
    root.option_add('*Text.background', colors['inputbg'])
    root.option_add('*Text.foreground', colors['fg'])
    root.option_add('*Text.insertBackground', colors['accent'])
    root.option_add('*Text.selectBackground', colors['selectbg'])
    root.option_add('*Text.selectForeground', colors['selectfg'])

    # Canvas (for scrollable areas)
    root.option_add('*Canvas.background', colors['bg'])
    root.option_add('*Canvas.highlightBackground', colors['bg'])


def apply_dark_theme(root):
    """
    Apply Dark Theme: Black, gray, and taupe shades.
    Sophisticated and moody pairing with lightest shade as background.
    """
    style = ttk.Style()

    # Sophisticated dark palette
    colors = {
        'bg': '#2b2b2b',           # Taupe-gray background (lightest)
        'fg': '#e8e6e3',           # Light taupe text
        'darkbg': '#1a1a1a',       # Deep black for contrast
        'selectbg': '#3d3d3d',     # Medium gray for selections
        'selectfg': '#ffffff',     # Pure white for selected text
        'border': '#4a4a4a',       # Gray borders
        'inputbg': '#1e1e1e',      # Dark gray for inputs
        'inputfg': '#d4d2cf',      # Light taupe for input text
        'button': '#3a3a3a',       # Medium gray buttons
        'buttontext': '#e8e6e3',   # Light taupe button text
        'accent': '#8b8680',       # Taupe accent
        'highlight': '#a39e93',    # Light taupe highlight
    }

    # Apply theme colors
    style.configure('.',
        background=colors['bg'],
        foreground=colors['fg'],
        bordercolor=colors['border'],
        darkcolor=colors['darkbg'],
        lightcolor=colors['accent'],
        troughcolor=colors['inputbg'],
        selectbackground=colors['selectbg'],
        selectforeground=colors['selectfg'],
        insertcolor=colors['fg'],
        fieldbackground=colors['inputbg'],
        font=('Segoe UI', 10)
    )

    # Frame styles
    style.configure('TFrame', background=colors['bg'])
    style.configure('TLabelframe', background=colors['bg'], foreground=colors['fg'], bordercolor=colors['accent'])
    style.configure('TLabelframe.Label', background=colors['bg'], foreground=colors['highlight'])

    # Label styles
    style.configure('TLabel', background=colors['bg'], foreground=colors['fg'])

    # Button styles
    style.configure('TButton',
        background=colors['button'],
        foreground=colors['buttontext'],
        bordercolor=colors['border'],
        darkcolor=colors['darkbg'],
        lightcolor=colors['accent'],
        relief='flat',
        font=('Segoe UI', 10)
    )

    style.map('TButton',
        background=[('active', colors['selectbg']), ('pressed', colors['darkbg'])],
        foreground=[('active', colors['selectfg']), ('pressed', colors['fg'])],
        bordercolor=[('active', colors['accent'])]
    )

    # Entry styles
    style.configure('TEntry',
        fieldbackground=colors['inputbg'],
        foreground=colors['inputfg'],
        bordercolor=colors['border'],
        insertcolor=colors['fg'],
        selectbackground=colors['selectbg'],
        selectforeground=colors['selectfg']
    )

    # Combobox styles
    style.configure('TCombobox',
        fieldbackground=colors['inputbg'],
        foreground=colors['inputfg'],
        background=colors['inputbg'],
        bordercolor=colors['border'],
        arrowcolor=colors['accent'],
        selectbackground=colors['selectbg'],
        selectforeground=colors['selectfg']
    )

    # Treeview styles
    style.configure('Treeview',
        background=colors['inputbg'],
        foreground=colors['fg'],
        fieldbackground=colors['inputbg'],
        bordercolor=colors['border'],
        selectbackground=colors['selectbg'],
        selectforeground=colors['selectfg']
    )

    style.configure('Treeview.Heading',
        background=colors['button'],
        foreground=colors['buttontext'],
        bordercolor=colors['border'],
        relief='flat'
    )

    # Scrollbar styles
    style.configure('TScrollbar',
        background=colors['button'],
        troughcolor=colors['bg'],
        bordercolor=colors['border'],
        arrowcolor=colors['accent']
    )

    # Text widget
    root.option_add('*Text.background', colors['inputbg'])
    root.option_add('*Text.foreground', colors['fg'])
    root.option_add('*Text.insertBackground', colors['accent'])
    root.option_add('*Text.selectBackground', colors['selectbg'])
    root.option_add('*Text.selectForeground', colors['selectfg'])

    # Canvas
    root.option_add('*Canvas.background', colors['bg'])
    root.option_add('*Canvas.highlightBackground', colors['bg'])
