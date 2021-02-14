from .boundingbox import BoundingBox

from kivy.graphics import Translate, Fbo, ClearColor, ClearBuffers, Scale
from kivy.uix.camera import Camera
from kivy.lang import Builder
from kivy.properties import ListProperty, BooleanProperty

from PIL import Image
import numpy as np

import face_recognition as fr


class FaceCamera(Camera):
    """
    Subclass of the Kivy camera class with support for realtime face detection
    and image capturing.
    """

    detected_faces = ListProperty([])
    '''
    List with the names of the currently detected faces.
    '''

    face_locations = ListProperty([])
    '''
    List of locations of the currently detected faces. The coordinates are 
    relative to the texture size.
    '''

    border_color = ListProperty((1, 0, 0, 1))
    '''
    Color of the bounding box around a face.
    '''

    label_color = ListProperty((1, 1, 1, 1))
    '''
    Text color of the label which displays the name of a person.
    '''

    enable_face_detection = BooleanProperty(True)
    '''
    Enable or disable face detection and thereby the callbacks:
    - on_face_locations
    - on_detected_faces
    '''

    def capture_image(self, filename):
        """
        Capture only the visible part of the camera, without the black border.
        Similar to export_to_png but with adjusted coordinates.
        :param filename: path to the target file name
        :return True
        """
        if self.parent is not None:
            canvas_parent_index = self.parent.canvas.indexof(self.canvas)
            if canvas_parent_index > -1:
                self.parent.canvas.remove(self.canvas)

        nw, nh = self.norm_image_size
        fbo = Fbo(size=(nw, nh), with_stencilbuffer=True)

        with fbo:
            ClearColor(0, 0, 0, 0)
            ClearBuffers()
            Scale(1, -1, 1)
            x = -self.x-(self.width-nw)/2
            y = -self.y-(self.height-nh)/2 - nh
            Translate(x, y, 0)

        fbo.add(self.canvas)
        fbo.draw()
        fbo.texture.save(filename, flipped=False)
        fbo.remove(self.canvas)

        if self.parent is not None and canvas_parent_index > -1:
            self.parent.canvas.insert(canvas_parent_index, self.canvas)

        return True

    def register_person(self, name, image):
        """
        Learn to identify a person, by providing a sample image with the
        corresponding name of the person.
        :param name: name of the person
        :param image: path to the image file
        """
        img = fr.load_image_file(image)
        enc = fr.face_encodings(img)[0]
        self._known_names.append(name)
        self._known_faces.append(enc)

    def __init__(self, *args, **kwargs):
        super(FaceCamera, self).__init__(*args, **kwargs)

        self._known_faces = []
        self._known_names = []

        # bounding boxes for each face
        self._bounding_boxes = []

    def on_tex(self, cam):
        super(FaceCamera, self).on_tex(cam)

        if not self.enable_face_detection:
            return

        # down scale factor for the image to speed up face detection
        scale = 6
        # get texture from camera object and create a pillow image
        # from the raw data
        tex = cam.texture
        im = Image.frombytes('RGBA', tex.size, tex.pixels, 'raw')
        im = im.resize((tex.width//scale, tex.height//scale))
        # convert image to np.array without alpha channel
        arr = np.array(im)[:,:,:3]
        # get face locations from the resized image
        locations = fr.face_locations(arr, number_of_times_to_upsample=1)#,
                                      #model="hog")
        # get face encodings for identification
        encodings = fr.face_encodings(arr, known_face_locations=locations,
                                      num_jitters=1)

        # update the face and location information
        faces = []
        for enc in encodings:
            # get name of the person
            matches = fr.compare_faces(self._known_faces, enc)#, tolerance=0.8)
            name = "Unknown"

            # use the first match which is found
            if True in matches:
                name = self._known_names[matches.index(True)]

            faces.append(name)

        # sort faces array and location array based on the name of face
        indices = np.argsort(faces)
        self.detected_faces = [f for f, i in sorted(zip(faces, indices),
                                                    key=lambda e: e[1])]
        self.face_locations = [(v*scale for v in l)
                               for l, i in sorted(zip(locations, indices),
                                                  key=lambda e: e[1])]

    def on_enable_face_detection(self, camera, enable):
        """
        Called when the face detection is enabled or disabled.
        :param camera: instance of this class
        :param enable: True if face detection is enable, otherwise false
        """
        # reset faces and location arrays
        self.detected_faces = []
        self.face_locations = []

        # detect faces if this feature is activated
        if enable:
            self.on_tex(self._camera)

    def on_detected_faces(self, camera, faces):
        """
        Called when the detected faces change.
        :param camera: instance of this class
        :param faces: array containing the name of each face
        """
        # remove old bounding boxes
        for bbox in self._bounding_boxes:
            self.remove_widget(bbox)
        self._bounding_boxes = []

        # add bounding boxes for each face
        for face_name in faces:
            bbox = BoundingBox(name=face_name, size_hint=(None, None))
            self._bounding_boxes.append(bbox)
            self.add_widget(bbox)

    def on_face_locations(self, camera, locations):
        """
        Called when the location of the faces change. The location for each face
        is give by (top, right, bottom, left) coordinates relative to the
        cameras texture.
        :param camera: instance of this class
        :param locations: array with new locations for each face
        """
        # fix the position of the rectangle
        for loc, bbox in zip(locations, self._bounding_boxes):
            # calculate texture size and actual image size
            rw, rh = self.texture.size
            nw, nh = self.norm_image_size
            # calculate scale factor caused by allow_stretch=True and/or
            # keep_ratio = False
            sw, sh = nw/rw, nh/rh

            anchor_t = self.center[1]+nh/2
            anchor_l = self.center[0]-nw/2

            # calculate position of the face
            t, r, b, l = loc
            t = anchor_t - t*sh
            b = anchor_t - b*sh
            r = anchor_l + r*sw
            l = anchor_l + l*sw

            # update bounding box
            bbox.border_color = self.border_color
            bbox.label.color = self.label_color
            bbox.pos = (l, b)
            bbox.size = (r-l, t-b)
