STYLESHEET = """
QWidget { color: #ededf2; font-family: 'Manrope'; font-size: 13px; font-weight: 400; }
QMainWindow { background: transparent; }
QWidget#Workspace { background: #0b0b0e; border: 1px solid #30243f; border-radius: 16px; }
QWidget#WindowBar { background: #101016; border-bottom: 1px solid #30243f; }
QFrame#Panel { background: rgba(167,139,250,18); border: 1px solid rgba(167,139,250,36); border-radius: 14px; }
QFrame#Hero { background: qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 #211831,stop:0.65 #14111d,stop:1 #111016); border: 1px solid #403052; border-radius: 14px; }
QLabel { background: transparent; border: none; }
QLabel#Brand { font-family:'Golos Text'; font-size: 20px; font-weight: 800; }
QLabel#Title { font-family:'Golos Text'; font-size: 32px; font-weight: 800; }
QLabel#HeroTitle { font-family:'Golos Text'; font-size: 36px; font-weight: 800; }
QLabel#Section { font-family:'Golos Text'; font-size: 17px; font-weight: 700; }
QLabel#Muted { color: #aaa3b8; }
QLabel#FieldLabel { color: #ded7e8; font-weight: 600; }
QLabel#Accent { color: #bfa6ff; }
QLabel#Metric { font-family:'JetBrains Mono'; font-size: 25px; font-weight: 400; }
QLabel#Score { font-family:'Golos Text'; font-size: 34px; font-weight: 800; }
QLabel#Status { padding: 6px 10px; color: #c4b5fd; background: rgba(167,139,250,20); border: 1px solid #473658; border-radius: 8px; }
QLabel#Message { padding: 10px 12px; background: #211b2c; color: #daceec; border-radius: 8px; }
QLabel#Error { padding: 10px 12px; background: #2c1c27; color: #fbabb1; border-radius: 8px; }
QPushButton { background:#191420; border:1px solid #3e304f; border-radius:8px; padding:8px 12px; font-weight:600; }
QPushButton:hover { background:#292037; border-color:#7b60a3; }
QPushButton:focus { border:1px solid #c4b5fd; }
QPushButton:disabled { color:#756b83; background:#131117; border-color:#25202d; }
QComboBox,QLineEdit,QSpinBox,QDoubleSpinBox { background:#1b1725; border:1px solid #40334f; border-radius:8px; padding:8px 11px; min-height:20px; selection-background-color:#644c88; selection-color:#ffffff; }
QComboBox { padding-right:28px; }
QComboBox::drop-down { border:none; width:27px; }
QComboBox::down-arrow { width:12px; height:12px; }
QComboBox:focus,QLineEdit:focus,QSpinBox:focus,QDoubleSpinBox:focus { border-color:#a78bfa; background:#231b30; }
QComboBox:disabled,QLineEdit:disabled,QSpinBox:disabled,QDoubleSpinBox:disabled { color:#756b83; background:#111016; border-color:#292331; }
QComboBox QAbstractItemView { background:#191320; color:#ededf2; selection-background-color:#3b2d50; border:1px solid #544068; outline:0; padding:6px; }
QComboBox QAbstractItemView::item { padding:8px; min-height:26px; }
QSpinBox#NumericValue,QDoubleSpinBox#NumericValue { font-family:'JetBrains Mono'; font-size:13px; padding:7px 5px; }
QSlider::groove:horizontal { height:5px; background:#392c49; border-radius:2px; }
QSlider::sub-page:horizontal { background:#a78bfa; border-radius:2px; }
QSlider::handle:horizontal { width:16px; margin:-6px 0; background:#e0d2ff; border:1px solid #a78bfa; border-radius:8px; }
QSlider::handle:horizontal:hover { background:#ffffff; }
QSlider:disabled::sub-page:horizontal { background:#51445e; }
QTabWidget::pane { border:0; background:transparent; }
QTabBar::tab { color:#aaa3b8; padding:11px 17px; border-bottom:2px solid transparent; }
QTabBar::tab:selected { color:#d6c3ff; border-bottom-color:#a78bfa; }
QTabBar::tab:hover { color:#ededf2; background:#211a2c; }
QScrollArea { background:transparent; border:0; }
QWidget#SettingsContent { background:#121017; }
QScrollBar:vertical { background:transparent; width:8px; margin:2px; }
QScrollBar::handle:vertical { background:#62516f; border-radius:3px; min-height:30px; }
QScrollBar::add-line:vertical,QScrollBar::sub-line:vertical { height:0; }
QScrollBar::add-page:vertical,QScrollBar::sub-page:vertical { background:transparent; }
QProgressBar { border:0; background:#31263f; border-radius:3px; height:7px; }
QProgressBar::chunk { background:#a78bfa; border-radius:3px; }
QTableWidget { background:#121018; alternate-background-color:#1a1523; gridline-color:#30243f; border:0; selection-background-color:#392c4b; }
QTableWidget::item { padding:8px; border:0; }
QHeaderView::section { background:#1e1728; color:#b9afc7; border:0; padding:11px 8px; font-size:12px; font-weight:600; }
QToolTip { background:#21182e; color:#ededf2; border:1px solid #6b5286; padding:8px; }
QMenu { background:#191320; border:1px solid #5c456f; border-radius:8px; padding:6px; }
QMenu::item { padding:9px 20px; }
QMenu::item:selected { background:#38294a; }
QDialog,QMessageBox { background:#15111c; }
"""
