import sys
import cv2
import numpy as np
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QLabel, QPushButton,
    QVBoxLayout, QHBoxLayout, QFileDialog, QInputDialog, QMessageBox,
    QToolBar, QAction, QColorDialog
)
from PyQt5.QtGui import QImage, QPixmap, QIcon, QColor
from PyQt5.QtCore import Qt, QSize

class ImageLabel(QLabel):
    """
    صنف فرعي من QLabel للتعامل مع أحداث الماوس (الرسم) مع تحويل الإحداثيات بحيث
    تتوافق مع أبعاد الصورة الأصلية حتى عند تغيير حجم النافذة. يدعم الرسم بالقلم،
    ورسم دائرة ومستطيل.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAlignment(Qt.AlignCenter)
        self.parent = parent  # مرجع للنافذة الرئيسية
        self.drawing = False
        self.last_point = None      # يستخدم للرسم بالقلم (Freehand)
        self.start_point = None     # نقطة البداية عند رسم الدائرة أو المستطيل
        self.temp_image = None      # نسخة من الصورة قبل بدء رسم الشكل (للمعاينة)

    def mapToImageCoordinates(self, pos):
        """
        تحويل إحداثيات نقطة الفأرة (المستلمة بالنسبة للـ QLabel) إلى إحداثيات الصورة الأصلية.
        
        عند استخدام KeepAspectRatioByExpanding يتم ملء مساحة الـ QLabel بالصورة مع اقتصاص
        الأجزاء الزائدة، لذا نحسب الإزاحة (offset) ثم نحول الإحداثيات.
        """
        label_width = self.width()
        label_height = self.height()

        pixmap = self.pixmap()
        if pixmap is None:
            return pos.x(), pos.y()

        # حجم الصورة المعروضة بعد استخدام KeepAspectRatioByExpanding
        scaled_width = pixmap.width()
        scaled_height = pixmap.height()

        # الجزء الظاهر في الـ QLabel هو المنطقة المركزية
        offset_x = (scaled_width - label_width) / 2
        offset_y = (scaled_height - label_height) / 2

        # نحسب إحداثيات النقطة داخل الصورة المعروضة
        x_in_pixmap = pos.x() + offset_x
        y_in_pixmap = pos.y() + offset_y

        # تحويل الإحداثيات إلى إحداثيات الصورة الأصلية
        if self.parent.current_image is None:
            return int(x_in_pixmap), int(y_in_pixmap)
        orig_height, orig_width = self.parent.current_image.shape[:2]
        factor_x = orig_width / scaled_width
        factor_y = orig_height / scaled_height

        return int(x_in_pixmap * factor_x), int(y_in_pixmap * factor_y)

    def mousePressEvent(self, event):
        if self.parent.current_image is None:
            return

        # يبدأ الرسم فقط في حالة اختيار أحد أوضاع الرسم
        if self.parent.shape_mode in ['circle', 'rectangle']:
            if event.button() == Qt.LeftButton:
                self.drawing = True
                self.start_point = self.mapToImageCoordinates(event.pos())
                self.temp_image = self.parent.current_image.copy()
        elif self.parent.shape_mode == 'pen':
            if event.button() == Qt.LeftButton:
                self.drawing = True
                self.last_point = self.mapToImageCoordinates(event.pos())

    def mouseMoveEvent(self, event):
        if self.parent.current_image is None or not self.drawing:
            return

        # استخدام اللون المختار (self.parent.pen_color) بدلاً من اللون الثابت
        if self.parent.shape_mode == 'circle':
            current_point = self.mapToImageCoordinates(event.pos())
            dx = current_point[0] - self.start_point[0]
            dy = current_point[1] - self.start_point[1]
            radius = int(np.sqrt(dx * dx + dy * dy))
            preview = self.temp_image.copy()
            cv2.circle(preview, self.start_point, radius, self.parent.pen_color, 2)
            self.parent.current_image_display = preview
            self.parent.update_image_display(preview=True)
        elif self.parent.shape_mode == 'rectangle':
            current_point = self.mapToImageCoordinates(event.pos())
            preview = self.temp_image.copy()
            cv2.rectangle(preview, self.start_point, current_point, self.parent.pen_color, 2)
            self.parent.current_image_display = preview
            self.parent.update_image_display(preview=True)
        elif self.parent.shape_mode == 'pen':
            current_point = self.mapToImageCoordinates(event.pos())
            cv2.line(self.parent.current_image, self.last_point, current_point, self.parent.pen_color, 2)
            self.last_point = current_point
            self.parent.update_image_display()

    def mouseReleaseEvent(self, event):
        if self.parent.current_image is None or not self.drawing:
            return

        if self.parent.shape_mode == 'circle':
            current_point = self.mapToImageCoordinates(event.pos())
            dx = current_point[0] - self.start_point[0]
            dy = current_point[1] - self.start_point[1]
            radius = int(np.sqrt(dx * dx + dy * dy))
            final_img = self.temp_image.copy()
            cv2.circle(final_img, self.start_point, radius, self.parent.pen_color, 2)
            self.parent.current_image = final_img
            self.parent.history.append(final_img.copy())
            self.parent.update_image_display()
        elif self.parent.shape_mode == 'rectangle':
            current_point = self.mapToImageCoordinates(event.pos())
            final_img = self.temp_image.copy()
            cv2.rectangle(final_img, self.start_point, current_point, self.parent.pen_color, 2)
            self.parent.current_image = final_img
            self.parent.history.append(final_img.copy())
            self.parent.update_image_display()
        elif self.parent.shape_mode == 'pen':
            # عند انتهاء الرسم بالقلم، يتم حفظ الحالة الحالية
            self.parent.history.append(self.parent.current_image.copy())
        self.drawing = False

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.current_image = None           # الصورة الأصلية (مصفوفة NumPy)
        self.current_image_display = None   # صورة المعاينة أثناء الرسم
        self.shape_mode = None              # يمكن أن تكون 'pen' أو 'circle' أو 'rectangle'
        self.history = []                   # قائمة لتخزين تاريخ التعديلات (لزر الرجوع)
        self.pen_color = (0, 0, 255)          # اللون الافتراضي للرسم (BGR) - أحمر
        self.initUI()

    def initUI(self):
        self.setWindowTitle("تطبيق التعامل مع الصور والكاميرا باستخدام PyQt5")
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)

        # إنشاء شريط أدوات علوي مع استخدام الأيقونات فقط
        toolbar = QToolBar("Tools", self)
        toolbar.setIconSize(QSize(32, 32))
        toolbar.setToolButtonStyle(Qt.ToolButtonIconOnly)
        self.addToolBar(Qt.TopToolBarArea, toolbar)

        backAction = QAction(QIcon("icons/undo.png"), "رجوع", self)
        backAction.setToolTip("رجوع")
        backAction.triggered.connect(self.go_back)
        toolbar.addAction(backAction)

        toolbar.addSeparator()

        grayscaleAction = QAction(QIcon("icons/grayscale.png"), "تحويل للصورة الرمادية", self)
        grayscaleAction.setToolTip("تحويل للصورة الرمادية")
        grayscaleAction.triggered.connect(self.apply_grayscale)
        toolbar.addAction(grayscaleAction)

        mirrorAction = QAction(QIcon("icons/mirror.png"), "صورة مرآة", self)
        mirrorAction.setToolTip("صورة مرآة")
        mirrorAction.triggered.connect(self.apply_mirror)
        toolbar.addAction(mirrorAction)

        colorAction = QAction(QIcon("icons/color.png"), "تغيير لون الخط", self)
        colorAction.setToolTip("تغيير لون الخط")
        colorAction.triggered.connect(self.change_pen_color)
        toolbar.addAction(colorAction)

        penAction = QAction(QIcon("icons/pen.png"), "الرسم بالقلم", self)
        penAction.setToolTip("الرسم بالقلم")
        penAction.triggered.connect(self.start_pen_drawing)
        toolbar.addAction(penAction)

        circleAction = QAction(QIcon("icons/circle.png"), "رسم دائرة", self)
        circleAction.setToolTip("رسم دائرة")
        circleAction.triggered.connect(self.start_circle_drawing)
        toolbar.addAction(circleAction)

        rectAction = QAction(QIcon("icons/rectangle.png"), "رسم مستطيل", self)
        rectAction.setToolTip("رسم مستطيل")
        rectAction.triggered.connect(self.start_rectangle_drawing)
        toolbar.addAction(rectAction)

        # إنشاء عنصر عرض الصورة
        self.image_label = ImageLabel(self)
        self.image_label.setStyleSheet("background-color: gray;")
        self.image_label.setMinimumSize(400, 300)

        self.info_label = QLabel("لا توجد صورة")

        # إنشاء أزرار فتح، التقاط، وحفظ الصورة (تبقى خارج شريط الأدوات)
        openButton = QPushButton("فتح صورة")
        openButton.clicked.connect(self.open_image)

        captureButton = QPushButton("التقاط صورة")
        captureButton.clicked.connect(self.capture_image)

        saveButton = QPushButton("حفظ الصورة")
        saveButton.clicked.connect(self.save_image)

        bottomLayout = QHBoxLayout()
        bottomLayout.addWidget(openButton)
        bottomLayout.addWidget(captureButton)
        bottomLayout.addWidget(saveButton)

        # تنظيم التخطيط الرئيسي
        layout = QVBoxLayout()
        layout.addWidget(self.image_label)
        layout.addWidget(self.info_label)
        layout.addLayout(bottomLayout)

        self.central_widget.setLayout(layout)
        self.resize(800, 600)

    def resizeEvent(self, event):
        """عند تغيير حجم النافذة يتم تحديث عرض الصورة لتتلاءم مع حجم الـ QLabel."""
        self.update_image_display()
        super().resizeEvent(event)

    def update_image_display(self, preview=False):
        """
        تحديث عرض الصورة في الـ QLabel.
        إذا كان preview=True نعرض الصورة المؤقتة (المعاينة أثناء الرسم) وإلا نعرض الصورة الأصلية.
        يتم تحجيم الصورة باستخدام KeepAspectRatioByExpanding لملء مساحة الـ QLabel.
        """
        if self.current_image is None:
            return

        img_to_show = self.current_image_display if preview and self.current_image_display is not None else self.current_image
        rgb_image = cv2.cvtColor(img_to_show, cv2.COLOR_BGR2RGB)
        h, w, ch = rgb_image.shape
        bytes_per_line = ch * w
        qimg = QImage(rgb_image.data, w, h, bytes_per_line, QImage.Format_RGB888)
        
        scaled_pixmap = QPixmap.fromImage(qimg).scaled(
            self.image_label.size(), Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation
        )
        self.image_label.setPixmap(scaled_pixmap)
        self.update_image_info()

    def update_image_info(self):
        if self.current_image is not None:
            h, w = self.current_image.shape[:2]
            channels = self.current_image.shape[2] if len(self.current_image.shape) == 3 else 1
            self.info_label.setText(f"الأبعاد: {w}x{h}، عدد القنوات: {channels}")
        else:
            self.info_label.setText("لا توجد صورة")

    def go_back(self):
        """تنفيذ عملية الرجوع (Undo) بإعادة الحالة السابقة للصورة."""
        if self.history:
            self.current_image = self.history.pop()
            self.update_image_display()
        else:
            QMessageBox.information(self, "تنبيه", "لا يوجد عملية للرجوع")

    def open_image(self):
        fname, _ = QFileDialog.getOpenFileName(self, "فتح صورة", "", "Images (*.png *.jpg *.jpeg *.bmp)")
        if fname:
            img = cv2.imread(fname)
            if img is not None:
                self.current_image = img
                self.current_image_display = None
                self.history = []  # تفريغ التاريخ عند فتح صورة جديدة
                self.update_image_display()
            else:
                QMessageBox.critical(self, "خطأ", "فشل قراءة الصورة!")

    def capture_image(self):
        cap = cv2.VideoCapture(0)
        if not cap.isOpened():
            QMessageBox.critical(self, "خطأ", "لا يمكن فتح الكاميرا")
            return

        # السماح للكاميرا ببعض الوقت للتسخين من خلال التقاط عدة إطارات
        ret = False
        for i in range(10):
            ret, frame = cap.read()
        cap.release()

        if ret and frame is not None:
            self.current_image = frame
            self.current_image_display = None
            self.history = []  # تفريغ التاريخ عند التقاط صورة جديدة
            self.update_image_display()
        else:
            QMessageBox.critical(self, "خطأ", "فشل التقاط الصورة")

    def save_image(self):
        if self.current_image is None:
            QMessageBox.warning(self, "تنبيه", "لا توجد صورة لحفظها")
            return
        fname, _ = QFileDialog.getSaveFileName(self, "حفظ الصورة", "", "JPEG Files (*.jpg);;PNG Files (*.png)")
        if fname:
            cv2.imwrite(fname, self.current_image)
            QMessageBox.information(self, "تم الحفظ", "تم حفظ الصورة بنجاح")

    def change_pen_color(self):
        """فتح مربع حوار لاختيار لون الخط وتحديث اللون المُستخدم في الرسم."""
        # تحويل اللون الافتراضي من BGR إلى RGB لإنشاء QColor
        current_color = QColor(self.pen_color[2], self.pen_color[1], self.pen_color[0])
        color = QColorDialog.getColor(initial=current_color, title="اختر لون الخط", parent=self)
        if color.isValid():
            # تحويل اللون من RGB إلى BGR لاستخدامه مع OpenCV
            self.pen_color = (color.blue(), color.green(), color.red())

    def apply_grayscale(self):
        if self.current_image is None:
            QMessageBox.warning(self, "تنبيه", "لا توجد صورة مرفوعة")
            return
        self.history.append(self.current_image.copy())
        gray = cv2.cvtColor(self.current_image, cv2.COLOR_BGR2GRAY)
        self.current_image = cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)
        self.update_image_display()

    def apply_mirror(self):
        if self.current_image is None:
            QMessageBox.warning(self, "تنبيه", "لا توجد صورة مرفوعة")
            return
        self.history.append(self.current_image.copy())
        self.current_image = cv2.flip(self.current_image, 1)
        self.update_image_display()

    def start_pen_drawing(self):
        """تفعيل وضع الرسم بالقلم (الرسم الحر)."""
        if self.current_image is None:
            QMessageBox.warning(self, "تنبيه", "لا توجد صورة مرفوعة")
            return
        self.shape_mode = 'pen'

    def start_circle_drawing(self):
        if self.current_image is None:
            QMessageBox.warning(self, "تنبيه", "لا توجد صورة مرفوعة")
            return
        self.shape_mode = 'circle'
        # يبقى الوضع مفعلًا للسماح برسم أكثر من دائرة

    def start_rectangle_drawing(self):
        if self.current_image is None:
            QMessageBox.warning(self, "تنبيه", "لا توجد صورة مرفوعة")
            return
        self.shape_mode = 'rectangle'
        # يبقى الوضع مفعلًا للسماح برسم أكثر من مستطيل



if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())
