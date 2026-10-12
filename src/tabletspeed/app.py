from __future__ import annotations
import ctypes, json, logging, sys, time
from pathlib import Path
from PySide6.QtCore import Qt, QTimer, QPoint, QPointF, QRect
from PySide6.QtGui import QAction, QColor, QPainter, QFont, QFontDatabase, QGuiApplication, QKeySequence, QPolygonF, QIcon, QPixmap
from PySide6.QtWidgets import QApplication, QWidget, QSystemTrayIcon, QMenu, QMainWindow, QLabel, QVBoxLayout, QHBoxLayout, QPushButton, QComboBox, QDoubleSpinBox, QSlider, QCheckBox, QMessageBox, QFormLayout, QSpinBox, QFileDialog, QInputDialog, QColorDialog, QScrollArea, QGridLayout
from .config import SettingsStore, DEFAULTS, data_dir
from .metrics import Metrics
from .sources import CursorSource, TabletSource
from .obs_server import ObsServer
from .config import Profiles
from .metrics import physical_size, screen_to_physical, convert_distance
from .startup import is_autostart_enabled, set_autostart
from .hotkeys import Hotkeys
from .single_instance import SingleInstance

class Overlay(QWidget):
    def __init__(self, state):
        super().__init__(); self.state=state; self.data={}; self.drag=None; self.resize_start=None
        self.setWindowTitle("TabletSpeed Overlay")
        self.setWindowFlags(Qt.WindowType.Tool|Qt.WindowType.FramelessWindowHint|Qt.WindowType.WindowStaysOnTopHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.resize(state["overlay_width"],state["overlay_height"])
        rect=QRect(state["overlay_x"],state["overlay_y"],state["overlay_width"],state["overlay_height"])
        if not any(rect.intersects(screen.geometry()) for screen in QGuiApplication.screens()):
            area=QGuiApplication.primaryScreen().availableGeometry(); rect.moveTopLeft(area.topLeft()+QPoint(24,24))
        self.move(rect.topLeft())
        self.set_clickthrough(state["click_through"]); self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, state["overlay_topmost"])
    def set_clickthrough(self, enabled):
        self.state["click_through"]=enabled
        if sys.platform == "win32" and self.winId():
            hwnd=int(self.winId()); GWL_EXSTYLE=-20; WS_EX_LAYERED=0x80000; WS_EX_TRANSPARENT=0x20
            user=ctypes.windll.user32; ex=user.GetWindowLongW(hwnd,GWL_EXSTYLE)|WS_EX_LAYERED
            ex = (ex|WS_EX_TRANSPARENT) if enabled else (ex&~WS_EX_TRANSPARENT)
            user.SetWindowLongW(hwnd,GWL_EXSTYLE,ex)
    def update_data(self, data): self.data=data; self.update()
    def paintEvent(self, event):
        p=QPainter(self); p.setRenderHint(QPainter.RenderHint.Antialiasing)
        bg=QColor(self.state["background"]); bg.setAlphaF(float(self.state["opacity"]))
        p.setBrush(bg); p.setPen(QColor(self.state["accent"])); p.drawRoundedRect(self.rect().adjusted(1,1,-2,-2),10,10)
        font=QFont(self.state.get("font_family","Segoe UI"),int(self.state["font_size"]),QFont.Weight.DemiBold); p.setFont(font)
        d=self.data; compact=self.state.get("compact",False)
        rows=[]
        if self.state.get("show_source",True): rows.append((str(d.get("source","Cursor")),self.state["foreground"]))
        if self.state.get("show_current",True): rows.append((("SPD " if compact else "SPEED ")+f"{d.get('speed',0):,.1f} {d.get('unit','px/s')}",self.state.get("current_color",self.state["accent"])))
        if self.state.get("show_average",True): rows.append((("AVG " if compact else "AVERAGE ")+f"{d.get('average',0):,.1f}",self.state.get("average_color",self.state["foreground"])))
        if self.state.get("show_max",True): rows.append((("MAX " if compact else "MAP MAX ")+f"{d.get('max',0):,.1f}  S {d.get('session_max',0):,.1f}",self.state.get("max_color",self.state["accent"])))
        if self.state.get("show_map_distance",True): rows.append((("MAP " if compact else "MAP DISTANCE ")+f"{d.get('distance',0):,.1f} {d.get('distance_unit','px')}",self.state.get("distance_color",self.state["foreground"])))
        if self.state.get("show_session_distance",True): rows.append((("SESSION " if compact else "SESSION DISTANCE ")+f"{d.get('session_distance',0):,.1f} {d.get('distance_unit','px')}",self.state.get("distance_color",self.state["foreground"])))
        fm=p.fontMetrics(); row_height=max(fm.height()+2,18); y=10; x=14
        for label,color in rows:
            p.setPen(QColor(color))
            if self.state.get("layout_orientation","vertical")=="horizontal":
                width=fm.horizontalAdvance(label)+16
                if x+width>self.width()-8: x=14; y+=row_height
                p.drawText(x,y,width,row_height,Qt.AlignmentFlag.AlignVCenter|Qt.AlignmentFlag.AlignLeft,label); x+=width
            else:
                p.drawText(14,y,self.width()-28,row_height,Qt.AlignmentFlag.AlignVCenter|Qt.AlignmentFlag.AlignLeft,label); y+=row_height
        if self.state.get("graph_visible",True) and len(d.get("history",[]))>1:
            points=d["history"][-80:]; hi=max(points) or 1.0; graph=QPolygonF()
            left,right=14.0,float(self.width()-14); top,bottom=float(self.height()-42),float(self.height()-14)
            for i,value in enumerate(points): graph.append(QPointF(left+(right-left)*i/max(1,len(points)-1),bottom-(bottom-top)*value/hi))
            p.setPen(QColor(self.state["accent"])); p.drawPolyline(graph)
    def mousePressEvent(self,e):
        if e.button()==Qt.MouseButton.LeftButton and not self.state["click_through"]:
            if e.position().x() >= self.width()-18 and e.position().y() >= self.height()-18:
                self.resize_start=(e.globalPosition().toPoint(),self.size())
            else: self.drag=e.globalPosition().toPoint()-self.frameGeometry().topLeft()
    def mouseMoveEvent(self,e):
        if self.resize_start and e.buttons() & Qt.MouseButton.LeftButton:
            origin,size=self.resize_start; delta=e.globalPosition().toPoint()-origin
            self.resize(max(180,size.width()+delta.x()),max(100,size.height()+delta.y()))
        elif self.drag is not None and e.buttons() & Qt.MouseButton.LeftButton: self.move(e.globalPosition().toPoint()-self.drag)
    def mouseReleaseEvent(self,e): self.drag=None; self.resize_start=None
    def closeEvent(self,e): self.state.update(overlay_x=self.x(),overlay_y=self.y(),overlay_width=self.width(),overlay_height=self.height()); e.accept()

class Settings(QMainWindow):
    def __init__(self,state,callback,shutdown):
        super().__init__(); self.state=state; self.callback=callback; self.shutdown=shutdown
        self.tray_available=True
        self.setWindowTitle("TabletSpeed — Settings"); self.resize(state.get("settings_width",620),state.get("settings_height",560))
        rect=QRect(state.get("settings_x",0),state.get("settings_y",0),state.get("settings_width",620),state.get("settings_height",560))
        if (state.get("settings_x",0) or state.get("settings_y",0)) and not any(rect.intersects(screen.geometry()) for screen in QGuiApplication.screens()):
            area=QGuiApplication.primaryScreen().availableGeometry(); rect.moveTopLeft(area.topLeft()+QPoint(36,36))
        if state.get("settings_x",0) or state.get("settings_y",0): self.move(rect.topLeft())
        root=QWidget(); outer=QVBoxLayout(root); outer.addWidget(QLabel("<h1 style='color:#33eaff'>TABLET SPEED</h1><p>Live cursor measurements for osu!</p>"))
        self.status=QLabel("Source: Windows cursor"); self.status.setWordWrap(True); outer.addWidget(self.status)
        form_panel=QWidget(); form=QFormLayout(form_panel); scroll=QScrollArea(); scroll.setWidgetResizable(True); scroll.setWidget(form_panel); outer.addWidget(scroll,1)
        self.source=QComboBox(); self.source.addItems(["Windows cursor","OpenTabletDriver IPC (plugin required)"]); form.addRow("Coordinate source",self.source)
        self.smooth=QDoubleSpinBox(); self.smooth.setRange(0,1); self.smooth.setSingleStep(.05); form.addRow("Speed smoothing (0–1)",self.smooth)
        self.noise=QDoubleSpinBox(); self.noise.setRange(0,500); self.noise.setSuffix(" native units"); form.addRow("Noise threshold",self.noise)
        self.average_window=QDoubleSpinBox(); self.average_window.setRange(.25,30); self.average_window.setSingleStep(.25); self.average_window.setSuffix(" s"); form.addRow("Average speed window",self.average_window)
        self.speed_units=QComboBox(); self.speed_units.addItems(["cm/s","mm/s"]); form.addRow("Calibrated speed unit",self.speed_units)
        self.distance_units=QComboBox(); self.distance_units.addItems(["mm","cm","m","km"]); form.addRow("Calibrated distance unit",self.distance_units)
        self.opacity=QSlider(Qt.Orientation.Horizontal); self.opacity.setRange(20,100); form.addRow("Overlay opacity",self.opacity)
        self.top=QCheckBox("Keep overlay above other windows"); form.addRow("Overlay",self.top)
        self.pass_mouse=QCheckBox("Click-through (recommended for gameplay)"); form.addRow("Interaction",self.pass_mouse)
        self.show_overlay=QCheckBox("Show overlay"); form.addRow("Visibility",self.show_overlay)
        self.graph_visible=QCheckBox("Show mini speed graph"); form.addRow("Graph",self.graph_visible)
        self.autostart=QCheckBox("Start TabletSpeed when I sign in"); form.addRow("Windows",self.autostart)
        self.font_size=QSpinBox(); self.font_size.setRange(8,48); form.addRow("Text size",self.font_size)
        font_row=QHBoxLayout(); self.font_label=QLabel(state.get("font_family","Segoe UI")); font_row.addWidget(self.font_label); font_button=QPushButton("Load TTF/OTF…"); font_button.clicked.connect(self.load_font); font_row.addWidget(font_button); form.addRow("Font",font_row)
        self.orientation=QComboBox(); self.orientation.addItems(["Vertical","Horizontal"]); form.addRow("Element layout",self.orientation)
        self.overlay_width=QSpinBox(); self.overlay_width.setRange(180,1200); form.addRow("Overlay width",self.overlay_width)
        self.overlay_height=QSpinBox(); self.overlay_height.setRange(100,900); form.addRow("Overlay height",self.overlay_height)
        self.obs_port=QSpinBox(); self.obs_port.setRange(1024,65535); form.addRow("OBS localhost port",self.obs_port)
        obs_buttons=QHBoxLayout(); obs_start=QPushButton("Start / stop Browser Source"); obs_start.clicked.connect(lambda:callback("obs")); obs_buttons.addWidget(obs_start); obs_copy=QPushButton("Copy Browser Source URL"); obs_copy.clicked.connect(lambda:callback("copy_obs_url")); obs_buttons.addWidget(obs_copy); form.addRow("OBS",obs_buttons)
        self.diagonal=QDoubleSpinBox(); self.diagonal.setRange(1,100); self.diagonal.setSuffix(" cm"); self.diagonal.setValue(20); form.addRow("Tablet physical diagonal (optional)",self.diagonal)
        self.aspect=QDoubleSpinBox(); self.aspect.setRange(.2,5); self.aspect.setSingleStep(.01); self.aspect.setValue(16/9); form.addRow("Whole-device aspect ratio",self.aspect)
        self.physical_preview=QLabel("Device diagonal is informational. Enter active area and mapped screen size for cm measurements."); form.addRow("Size preview",self.physical_preview)
        self.active_width=QDoubleSpinBox(); self.active_width.setRange(0,80); self.active_width.setDecimals(2); self.active_width.setSuffix(" cm"); form.addRow("Active tablet width (0 = uncalibrated)",self.active_width)
        self.active_height=QDoubleSpinBox(); self.active_height.setRange(0,80); self.active_height.setDecimals(2); self.active_height.setSuffix(" cm"); form.addRow("Active tablet height",self.active_height)
        self.mapped_width=QDoubleSpinBox(); self.mapped_width.setRange(0,20000); self.mapped_width.setDecimals(0); self.mapped_width.setSuffix(" px"); form.addRow("Mapped screen width",self.mapped_width)
        self.mapped_height=QDoubleSpinBox(); self.mapped_height.setRange(0,20000); self.mapped_height.setDecimals(0); self.mapped_height.setSuffix(" px"); form.addRow("Mapped screen height",self.mapped_height)
        self.show_current=QCheckBox("Current speed"); self.show_average=QCheckBox("Average speed"); self.show_max=QCheckBox("Map and session maximum"); self.show_map_distance=QCheckBox("Map distance"); self.show_session_distance=QCheckBox("Session distance"); self.show_source=QCheckBox("Source label"); self.compact=QCheckBox("Compact labels")
        layout_row=QGridLayout()
        for i,w in enumerate((self.show_current,self.show_average,self.show_max,self.show_map_distance,self.show_session_distance,self.show_source,self.compact)): layout_row.addWidget(w,i//3,i%3)
        form.addRow("Overlay elements",layout_row)
        self.preset=QComboBox(); self.preset.addItems(["Cyberpunk","Neon Blue","Neon Purple","Minimal Dark","Monochrome"]); form.addRow("Color preset",self.preset); self.preset.activated.connect(self.apply_preset)
        color_row=QHBoxLayout()
        for key,label in (("accent","Accent"),("foreground","Text"),("background","Background"),("current_color","Current"),("average_color","Average"),("max_color","Maximum"),("distance_color","Distance")):
            b=QPushButton(label); b.clicked.connect(lambda checked=False,k=key:self.choose_color(k)); color_row.addWidget(b)
        form.addRow("Colors",color_row)
        buttons=QGridLayout(); outer.addLayout(buttons)
        for i,(label,fn) in enumerate([("New map / reset map",lambda:callback("reset_map")),("Reset session",lambda:callback("reset_session")),("Reset all…",self.confirm_reset_all),("Profiles…",lambda:callback("profiles")),("Toggle overlay lock",lambda:callback("unlock")),("Exit",shutdown)]):
            b=QPushButton(label); b.clicked.connect(fn); buttons.addWidget(b,i//3,i%3)
        self.setCentralWidget(root); self.sync_from_state()
        self.source.currentIndexChanged.connect(self.source_changed); self.smooth.valueChanged.connect(self.changed); self.noise.valueChanged.connect(self.changed); self.average_window.valueChanged.connect(self.changed); self.speed_units.currentIndexChanged.connect(self.changed); self.distance_units.currentIndexChanged.connect(self.changed); self.opacity.valueChanged.connect(self.changed); self.top.toggled.connect(self.changed); self.pass_mouse.toggled.connect(self.changed); self.show_overlay.toggled.connect(self.changed); self.graph_visible.toggled.connect(self.changed); self.orientation.currentIndexChanged.connect(self.changed); self.show_current.toggled.connect(self.changed); self.show_average.toggled.connect(self.changed); self.show_max.toggled.connect(self.changed); self.show_map_distance.toggled.connect(self.changed); self.show_session_distance.toggled.connect(self.changed); self.show_source.toggled.connect(self.changed); self.compact.toggled.connect(self.changed); self.autostart.toggled.connect(self.autostart_changed); self.font_size.valueChanged.connect(self.changed); self.overlay_width.valueChanged.connect(self.changed); self.overlay_height.valueChanged.connect(self.changed); self.obs_port.valueChanged.connect(self.changed); self.active_width.valueChanged.connect(self.changed); self.active_height.valueChanged.connect(self.changed); self.mapped_width.valueChanged.connect(self.changed); self.mapped_height.valueChanged.connect(self.changed); self.diagonal.valueChanged.connect(self.update_area_preview); self.aspect.valueChanged.connect(self.update_area_preview)
    def sync_from_state(self):
        s=self.state; self.source.setCurrentIndex(0 if s["source"]=="cursor" else 1); self.smooth.setValue(s["smoothing"]); self.noise.setValue(s["noise_threshold"]); self.average_window.setValue(s.get("average_window",2)); self.speed_units.setCurrentIndex(1 if s.get("physical_speed_unit")=="mm/s" else 0); self.distance_units.setCurrentText(s.get("distance_display_unit","cm")); self.opacity.setValue(int(s["opacity"]*100)); self.top.setChecked(s["overlay_topmost"]); self.pass_mouse.setChecked(s["click_through"]); self.show_overlay.setChecked(s["overlay_visible"]); self.graph_visible.setChecked(s.get("graph_visible",True)); self.show_current.setChecked(s.get("show_current",True)); self.show_average.setChecked(s.get("show_average",True)); self.show_max.setChecked(s.get("show_max",True)); self.show_map_distance.setChecked(s.get("show_map_distance",True)); self.show_session_distance.setChecked(s.get("show_session_distance",True)); self.show_source.setChecked(s.get("show_source",True)); self.compact.setChecked(s.get("compact",False)); self.autostart.setChecked(s.get("autostart",False)); self.font_size.setValue(s["font_size"]); self.font_label.setText(s.get("font_family","Segoe UI")); self.orientation.setCurrentIndex(1 if s.get("layout_orientation")=="horizontal" else 0); self.overlay_width.setValue(s["overlay_width"]); self.overlay_height.setValue(s["overlay_height"]); self.obs_port.setValue(s.get("obs_port",8765)); self.diagonal.setValue(s.get("tablet_diagonal_cm",20)); self.aspect.setValue(s.get("tablet_aspect",16/9)); self.active_width.setValue(s.get("active_width_cm",0)); self.active_height.setValue(s.get("active_height_cm",0)); self.mapped_width.setValue(s.get("mapped_width_px",0)); self.mapped_height.setValue(s.get("mapped_height_px",0)); self.update_area_preview()
    def update_area_preview(self,*_):
        try:
            w,h=physical_size(self.diagonal.value(),self.aspect.value()); self.physical_preview.setText(f"Whole device: {w:.2f} × {h:.2f} cm. This is not the active area.")
        except ValueError: self.physical_preview.setText("Enter a positive diagonal and aspect ratio.")
    def load_font(self):
        path,_=QFileDialog.getOpenFileName(self,"Choose font","","Fonts (*.ttf *.otf)")
        if not path: return
        font_id=QFontDatabase.addApplicationFont(path)
        families=QFontDatabase.applicationFontFamilies(font_id) if font_id>=0 else []
        if not families:
            QMessageBox.warning(self,"Font","This TTF/OTF file could not be loaded."); return
        self.state.update(font_file=path,font_family=families[0]); self.font_label.setText(families[0]); self.callback("settings")
    def apply_preset(self,index):
        palettes=[("#33eaff","#f4f7ff","#101020"),("#00c8ff","#eafaff","#071523"),("#bd70ff","#f7efff","#170d25"),("#a8b0bf","#f4f4f4","#15171b"),("#ffffff","#ffffff","#000000")]
        self.state.update(zip(("accent","foreground","background"),palettes[index])); self.callback("settings")
    def choose_color(self,key):
        color=QColorDialog.getColor(QColor(self.state[key]),self,f"Choose {key} color")
        if color.isValid(): self.state[key]=color.name(); self.callback("settings")
    def confirm_reset_all(self):
        answer=QMessageBox.question(self,"Reset all statistics?","This clears map and session distances, speed averages and maximums.",QMessageBox.StandardButton.Yes|QMessageBox.StandardButton.No,QMessageBox.StandardButton.No)
        if answer==QMessageBox.StandardButton.Yes: self.callback("reset_all")
    def source_changed(self,index):
        self.changed()
    def autostart_changed(self,enabled):
        self.state["autostart"]=bool(enabled); self.callback("autostart")
    def changed(self,*_):
        self.state.update(source="cursor" if self.source.currentIndex()==0 else "tablet",smoothing=self.smooth.value(),noise_threshold=self.noise.value(),average_window=self.average_window.value(),physical_speed_unit=self.speed_units.currentText(),distance_display_unit=self.distance_units.currentText(),opacity=self.opacity.value()/100,overlay_topmost=self.top.isChecked(),click_through=self.pass_mouse.isChecked(),overlay_visible=self.show_overlay.isChecked(),graph_visible=self.graph_visible.isChecked(),show_current=self.show_current.isChecked(),show_average=self.show_average.isChecked(),show_max=self.show_max.isChecked(),show_map_distance=self.show_map_distance.isChecked(),show_session_distance=self.show_session_distance.isChecked(),show_source=self.show_source.isChecked(),compact=self.compact.isChecked(),layout_orientation="horizontal" if self.orientation.currentIndex()==1 else "vertical",autostart=self.autostart.isChecked(),font_size=self.font_size.value(),overlay_width=self.overlay_width.value(),overlay_height=self.overlay_height.value(),obs_port=self.obs_port.value(),tablet_diagonal_cm=self.diagonal.value(),tablet_aspect=self.aspect.value(),active_width_cm=self.active_width.value(),active_height_cm=self.active_height.value(),mapped_width_px=self.mapped_width.value(),mapped_height_px=self.mapped_height.value()); self.callback("settings")
    def closeEvent(self,event):
        self.state.update(settings_x=self.x(),settings_y=self.y(),settings_width=self.width(),settings_height=self.height())
        self.callback("window_geometry")
        if self.tray_available: event.ignore(); self.hide()
        else: event.ignore(); self.showMinimized()
    def changeEvent(self,event):
        super().changeEvent(event)
        if event.type()==event.Type.WindowStateChange and self.isMinimized() and self.tray_available: QTimer.singleShot(0,self.hide)

class Controller:
    def __init__(self,app):
        self.app=app; self.store=SettingsStore(); self.state=self.store.load(); self.state["obs_enabled"]=False
        if sys.platform=="win32": self.state["autostart"]=is_autostart_enabled()
        self.profiles=Profiles()
        stored_profiles=self.profiles.load()
        if not self.profiles.path.exists(): self.profiles.save({"Default":dict(self.state)})
        if self.state.get("active_profile","Default") not in stored_profiles: self.state["active_profile"]="Default"
        font_path=self.state.get("font_file","")
        if font_path and Path(font_path).is_file():
            font_id=QFontDatabase.addApplicationFont(font_path)
            families=QFontDatabase.applicationFontFamilies(font_id) if font_id>=0 else []
            if families: self.state["font_family"]=families[0]
            else: self.state.update(font_file="",font_family="Segoe UI")
        elif font_path: self.state.update(font_file="",font_family="Segoe UI")
        self.metrics=Metrics(self.state["noise_threshold"],self.state["smoothing"],average_window=self.state.get("average_window",2)); self.source=CursorSource(); self.tablet_source=TabletSource(); self.last_input_time=0.0; self.last_error=""; self.metric_signature=self.measurement_config()
        self.overlay=Overlay(self.state); self.settings=Settings(self.state,self.action,self.quit)
        data_dir().joinpath("logs").mkdir(parents=True,exist_ok=True)
        from logging.handlers import RotatingFileHandler
        handler=RotatingFileHandler(data_dir()/"logs"/"tabletspeed.log",maxBytes=1_000_000,backupCount=3,encoding="utf-8")
        logging.basicConfig(level=logging.INFO,handlers=[handler],format="%(asctime)s %(levelname)s %(message)s")
        self.timer=QTimer(); self.timer.setInterval(16); self.timer.timeout.connect(self.tick); self.timer.start()
        self.instance=None; self.instance_timer=None
        self.tray=None; self.obs=None; self.make_tray(); self.apply_state()
        if self.state["source"]=="tablet":
            try: self.source.stop(); self.tablet_source.start()
            except Exception as exc: self.tablet_source.error=str(exc); self.last_error=str(exc)
        else: self.source.start()
        try: self.otd_socket=TabletSource.discover_socket()
        except (OSError,RuntimeError): self.otd_socket=None
        if self.otd_socket and self.state["source"]=="cursor" and self.tray:
            self.tray.showMessage("OpenTabletDriver detected","OTD-IPC is available. Select it in Settings to use direct tablet coordinates; the connection may disable OTD's normal output mode.")
        self.hotkeys=Hotkeys(); self.hotkey_errors=self.hotkeys.start({"O":lambda:self.action("toggle_overlay"),"N":lambda:self.action("reset_map"),"S":lambda:self.action("reset_session"),"M":lambda:self.action("reset_max"),"G":lambda:self.action("toggle_graph"),"L":lambda:self.action("unlock"),"P":self.open_settings})
        if self.hotkey_errors:
            if self.tray: self.tray.showMessage("TabletSpeed hotkeys", "\n".join(self.hotkey_errors))
            else: QMessageBox.warning(self.settings,"TabletSpeed hotkeys","\n".join(self.hotkey_errors))
    def open_settings(self):
        self.settings.showNormal(); self.settings.raise_(); self.settings.activateWindow()
    def set_instance_guard(self,instance):
        self.instance=instance; self.instance_timer=QTimer(self.app); self.instance_timer.setInterval(200)
        self.instance_timer.timeout.connect(lambda:self.open_settings() if self.instance.consume_activation() else None); self.instance_timer.start()
    def make_tray(self):
        if not QSystemTrayIcon.isSystemTrayAvailable():
            QMessageBox.warning(None,"TabletSpeed","System tray is unavailable. The settings window will remain available on the taskbar when minimized."); self.settings.tray_available=False; self.settings.show(); return
        self.tray=QSystemTrayIcon(self.app); self.tray.setToolTip("TabletSpeed")
        pix=QPixmap(32,32); pix.fill(Qt.GlobalColor.transparent); painter=QPainter(pix); painter.setPen(QColor("#33eaff")); painter.setBrush(QColor("#101020")); painter.drawRoundedRect(1,1,30,30,6,6); painter.setFont(QFont("Segoe UI",10,QFont.Weight.Bold)); painter.drawText(pix.rect(),Qt.AlignmentFlag.AlignCenter,"TS"); painter.end(); self.tray.setIcon(QIcon(pix))
        menu=QMenu(); self.overlay_action=menu.addAction("Hide overlay"); self.overlay_action.triggered.connect(lambda:self.action("toggle_overlay")); show=menu.addAction("Open settings"); show.triggered.connect(self.open_settings); menu.addSeparator()
        self.source_action=menu.addAction("Use OpenTabletDriver input"); self.source_action.setCheckable(True); self.source_action.setChecked(self.state["source"]=="tablet"); self.source_action.triggered.connect(lambda enabled:self.settings.source.setCurrentIndex(1 if enabled else 0))
        menu.addAction("Reset map statistics",lambda:self.action("reset_map")); menu.addAction("Reset session distance",lambda:self.action("reset_session")); menu.addAction("Reset all statistics…",self.settings.confirm_reset_all); menu.addAction("Restart coordinate source",lambda:self.action("restart_source")); menu.addAction("Start/stop OBS source",lambda:self.action("obs")); menu.addSeparator()
        self.autostart_action=menu.addAction("Run at Windows sign-in"); self.autostart_action.setCheckable(True); self.autostart_action.setChecked(bool(self.state.get("autostart",False))); self.autostart_action.triggered.connect(lambda checked:(setattr(self,"_auto_start_requested",checked),self.state.update(autostart=checked),self.action("autostart"))); menu.addSeparator(); menu.addAction("Exit",self.quit)
        self.tray.setContextMenu(menu); self.tray.activated.connect(lambda reason:self.open_settings() if reason==QSystemTrayIcon.ActivationReason.Trigger else None); self.tray.show()
    def apply_state(self):
        self.metrics.noise_threshold=float(self.state["noise_threshold"]); self.metrics.smoothing=float(self.state["smoothing"]); self.metrics.average_window=float(self.state.get("average_window",2))
        self.overlay.resize(int(self.state["overlay_width"]),int(self.state["overlay_height"]))
        self.overlay.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint,bool(self.state["overlay_topmost"])); self.overlay.set_clickthrough(bool(self.state["click_through"]))
        if self.state["overlay_visible"]: self.overlay.show()
        else: self.overlay.hide()
        if self.tray:
            self.overlay_action.setText("Hide overlay" if self.state["overlay_visible"] else "Show overlay")
            self.autostart_action.setChecked(bool(self.state.get("autostart",False)))
            self.source_action.setChecked(self.state.get("source")=="tablet")
        self.settings.obs_port.setEnabled(self.obs is None)
    def measurement_config(self):
        keys=("source","active_width_cm","active_height_cm","mapped_width_px","mapped_height_px")
        return {key:self.state.get(key,DEFAULTS.get(key)) for key in keys}
    def action(self, action):
        if action=="settings":
            new_config=self.measurement_config()
            if new_config!=self.metric_signature:
                if new_config["source"]=="tablet" and self.metric_signature["source"]!="tablet":
                    answer=QMessageBox.warning(self.settings,"OpenTabletDriver exclusive input","OTD-IPC takes exclusive access and may disable OpenTabletDriver's normal output mode while connected. osu! may stop receiving tablet motion. Continue only if you understand this limitation.",QMessageBox.StandardButton.Yes|QMessageBox.StandardButton.No,QMessageBox.StandardButton.No)
                    if answer!=QMessageBox.StandardButton.Yes:
                        self.state.update(self.metric_signature); self.settings.sync_from_state(); return
                m=self.metrics.measurement
                has_data=bool(m.map_distance or m.session_distance or m.max_speed or m.max_session_speed)
                if has_data:
                    answer=QMessageBox.question(self.settings,"Change measurement source/calibration?","Changing coordinate units or mapping resets current measurements. Continue?",QMessageBox.StandardButton.Yes|QMessageBox.StandardButton.No,QMessageBox.StandardButton.No)
                    if answer!=QMessageBox.StandardButton.Yes:
                        self.state.update(self.metric_signature); self.settings.sync_from_state(); return
                self.metrics.reset_all(); self.metric_signature=new_config; self.last_input_time=0.0
                if new_config["source"]=="tablet":
                    self.source.stop(); self.tablet_source.stop()
                    try: self.tablet_source.start()
                    except Exception as exc: self.tablet_source.error=str(exc); logging.exception("Could not start OTD IPC source")
                else:
                    self.tablet_source.stop(); self.source.start()
        if action=="toggle_overlay": self.state["overlay_visible"]=not self.state["overlay_visible"]
        elif action=="toggle_graph": self.state["graph_visible"]=not self.state.get("graph_visible",True)
        elif action=="reset_map": self.metrics.reset_map()
        elif action=="reset_session": self.metrics.reset_session()
        elif action=="reset_all": self.metrics.reset_all()
        elif action=="reset_max": self.metrics.reset_max_speed()
        elif action=="restart_source":
            self.metrics.previous=None
            try:
                if self.state["source"]=="tablet": self.tablet_source.stop(); self.tablet_source.start()
                else: self.source.stop(); self.source.start()
                self.settings.status.setText("Coordinate source restarted.")
            except Exception as exc: QMessageBox.warning(self.settings,"Coordinate source",str(exc))
        elif action=="unlock": self.state["click_through"]=not self.state["click_through"]
        elif action=="profiles": self.manage_profiles()
        elif action=="copy_obs_url":
            url=f"http://127.0.0.1:{int(self.state['obs_port'])}/"; QApplication.clipboard().setText(url); self.settings.status.setText(f"Copied OBS Browser Source URL: {url}")
        elif action=="obs":
            try:
                if self.obs: self.obs.stop(); self.obs=None; self.state["obs_enabled"]=False
                else: self.obs=ObsServer(self.snapshot,int(self.state["obs_port"])); self.obs.start(); self.state["obs_enabled"]=True
            except Exception as e: QMessageBox.warning(self.settings,"OBS source",str(e)); self.obs=None; self.state["obs_enabled"]=False
        if action=="autostart":
            try:
                set_autostart(bool(self.state["autostart"]))
            except OSError as exc:
                QMessageBox.warning(self.settings,"Autostart",str(exc)); self.state["autostart"]=False; self.settings.sync_from_state()
        self.apply_state(); self.settings.sync_from_state(); self.store.save(self.state)
        if action in {"settings","autostart","toggle_overlay","toggle_graph","unlock","window_geometry"}:
            profiles=self.profiles.load(); profiles[self.state.get("active_profile","Default")]=dict(self.state); self.profiles.save(profiles)
    def manage_profiles(self):
        profiles=self.profiles.load()
        names=list(profiles)
        active=self.state.get("active_profile","Default")
        if active in names: names.remove(active); names.insert(0,active)
        current,ok=QInputDialog.getItem(self.settings,"Profiles","Choose a profile",names,0,False)
        if ok and current:
            choice,yes=QInputDialog.getItem(self.settings,"Profiles","Action",["Apply","Save current as…","Rename…","Duplicate…","Delete","Export…","Import…"],0,False)
            if not yes: return
            if choice=="Apply": self.state.update(profiles[current]); self.state["active_profile"]=current; self.settings.sync_from_state(); self.action("settings")
            elif choice=="Save current as…":
                name,yes=QInputDialog.getText(self.settings,"Save profile","Profile name")
                if yes and name:
                    self.state["active_profile"]=name.strip(); profiles[name.strip()]=dict(self.state); self.profiles.save(profiles); self.store.save(self.state)
            elif choice=="Rename…":
                name,yes=QInputDialog.getText(self.settings,"Rename profile","New profile name",text=current)
                if yes and name.strip() and name.strip() not in profiles:
                    profiles[name.strip()]=profiles.pop(current)
                    if self.state.get("active_profile")==current: self.state["active_profile"]=name.strip()
                    self.profiles.save(profiles); self.store.save(self.state)
            elif choice=="Duplicate…":
                name,yes=QInputDialog.getText(self.settings,"Duplicate profile","New profile name")
                if yes and name: profiles[name.strip()]=dict(profiles[current]); self.profiles.save(profiles)
            elif choice=="Delete" and len(profiles)>1:
                del profiles[current]
                if self.state.get("active_profile")==current: self.state["active_profile"]=next(iter(profiles))
                self.profiles.save(profiles); self.store.save(self.state)
            elif choice=="Export…":
                path,_=QFileDialog.getSaveFileName(self.settings,"Export profile","profile.json","JSON (*.json)")
                if path: self.profiles.export_profile(current,Path(path))
            elif choice=="Import…":
                path,_=QFileDialog.getOpenFileName(self.settings,"Import profile","","JSON (*.json)")
                if path:
                    name,yes=QInputDialog.getText(self.settings,"Import profile","Profile name (optional)")
                    if yes:
                        try: self.profiles.import_profile(Path(path),name.strip() or None)
                        except (ValueError,OSError) as exc: QMessageBox.warning(self.settings,"Profile import",str(exc))
    def format_measurement(self,m,source,history=None):
        speed_unit=m.unit; distance_unit=m.unit.replace("/s",""); scale=1.0
        if m.unit=="cm/s":
            speed_unit=self.state.get("physical_speed_unit","cm/s"); scale=10.0 if speed_unit=="mm/s" else 1.0
            distance_unit=self.state.get("distance_display_unit","cm")
            distance=lambda value: convert_distance(value,"cm",distance_unit)
        else: distance=lambda value:value
        return {"speed":m.current_speed*scale,"average":m.average_speed*scale,"max":m.max_speed*scale,"session_max":m.max_session_speed*scale,"distance":distance(m.map_distance),"session_distance":distance(m.session_distance),"unit":speed_unit,"distance_unit":distance_unit,"history":[v*scale for v in (history or [])],"source":source}
    def snapshot(self):
        data=self.format_measurement(self.metrics.measurement,"TabletSpeed",[v for _,v in self.metrics.samples])
        data.update(accent=self.state["accent"],foreground=self.state["foreground"],background=self.state["background"],font_size=self.state["font_size"],opacity=self.state["opacity"])
        return data
    def tick(self):
        self.hotkeys.poll()
        try:
            if self.state["source"]=="tablet":
                if self.tablet_source.error:
                    self.settings.status.setText(f"OTD source error: {self.tablet_source.error}"); return
                pt=self.tablet_source.read()
                if pt is None:
                    if not self.last_input_time and not self.tablet_source.error: self.settings.status.setText(f"OTD connected · {self.tablet_source.device_name} · waiting for tablet input")
                    if self.last_input_time and time.perf_counter()-self.last_input_time>.25:
                        self.metrics.measurement.current_speed=0.0; self.metrics._smooth=0.0
                        m=self.metrics.measurement; unit=m.unit
                        payload=self.format_measurement(m,f"OTD · {self.tablet_source.device_name}",[speed for _,speed in self.metrics.samples]); payload["speed"]=0.0; self.overlay.update_data(payload)
                    return
                self.last_input_time=pt.timestamp
                physical=self.tablet_source.max_x>0 and self.tablet_source.max_y>0 and self.state["active_width_cm"]>0 and self.state["active_height_cm"]>0
                if physical:
                    x=pt.x*self.state["active_width_cm"]/self.tablet_source.max_x; y=pt.y*self.state["active_height_cm"]/self.tablet_source.max_y; unit="cm/s"; distance_unit="cm"
                else: x,y,unit,distance_unit=pt.x,pt.y,"du/s","du"
                source_label=f"OTD · {self.tablet_source.device_name}"
            else:
                pt=self.source.read()
                if pt is None:
                    if self.source.error:
                        if self.source.error!=self.last_error: logging.error("Cursor source failed: %s",self.source.error); self.last_error=self.source.error
                        self.settings.status.setText(f"Cursor source error: {self.source.error}")
                    return
                physical=all(float(self.state[k])>0 for k in ("active_width_cm","active_height_cm","mapped_width_px","mapped_height_px"))
                if physical:
                    x,y=screen_to_physical(pt.x,pt.y,self.state["mapped_width_px"],self.state["mapped_height_px"],self.state["active_width_cm"],self.state["active_height_cm"]); unit="cm/s"; distance_unit="cm"
                else: x,y,unit,distance_unit=pt.x,pt.y,"px/s","px"
                source_label="Windows cursor"
            m=self.metrics.add(x,y,pt.timestamp,unit)
            data=self.format_measurement(m,source_label,[speed for _,speed in self.metrics.samples])
            self.overlay.update_data(data); self.settings.status.setText(f"{source_label} · {data['speed']:.1f} {data['unit']} · session {data['session_distance']:.1f} {data['distance_unit']}")
            self.last_error=""
        except Exception as exc:
            message=str(exc)
            if message!=self.last_error: logging.exception("Coordinate source failed"); self.last_error=message
            self.settings.status.setText(f"Source error: {message}")
    def quit(self):
        self.timer.stop()
        if self.instance_timer: self.instance_timer.stop()
        self.hotkeys.stop(); self.tablet_source.stop(); self.source.stop()
        if self.obs: self.obs.stop()
        self.overlay.close(); self.store.save(self.state); self.settings.close();
        if self.tray: self.tray.hide()
        self.app.quit()

def main():
    app=QApplication(sys.argv); app.setApplicationName("TabletSpeed"); app.setQuitOnLastWindowClosed(False)
    if "--smoke-test" in sys.argv:
        QSystemTrayIcon.isSystemTrayAvailable=lambda:True
        instance=SingleInstance("Local\\TabletSpeed.SmokeTest")
        if not instance.acquire(): return 2
        try:
            c=Controller(app); c.set_instance_guard(instance); QTimer.singleShot(500,c.quit); return app.exec()
        finally: instance.close()
    instance=SingleInstance()
    try: is_primary=instance.acquire()
    except OSError as exc: QMessageBox.critical(None,"TabletSpeed",f"Could not create the single-instance guard: {exc}"); return 2
    if not is_primary: return 0
    try:
        controller=Controller(app); controller.set_instance_guard(instance)
        return app.exec()
    finally: instance.close()
