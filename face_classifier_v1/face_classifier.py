#!/usr/bin/env python3

from person import Person
from person import Face
import face_recognition
import numpy as np


class FaceClassifier():
    def __init__(self, threshold=0.55):
        self.known_persons = []
        self.unknown_faces = []
        self.similarity_threshold = threshold

    def get_face_image(self, frame, box):
        img_height, img_width = frame.shape[:2]
        (top, right, bottom, left) = box
        box_width = right - left
        box_height = bottom - top
        top = max(top - box_height, 0)
        bottom = min(bottom + box_height, img_height - 1)
        left = max(left - box_width, 0)
        right = min(right + box_width, img_width - 1)
        return frame[top:bottom, left:right]

    def detect_faces(self, second, frame):
        rgb = frame[:, :, ::-1]
        boxes = face_recognition.face_locations(rgb, model="hog")
        if not boxes:
            return []

        faces = []
        encodings = face_recognition.face_encodings(rgb, boxes)
        for box, encoding in zip(boxes, encodings):
            face_image = self.get_face_image(frame, box)
            face = Face(second, face_image, encoding)
            faces.append(face)
        return faces

    def classify_face(self, face):
        # collect encodings of the faces
        known_encodings = [person.encoding for person in self.known_persons]
        unknown_encodings = [face.encoding for face in self.unknown_faces]
        all_encodings = known_encodings + unknown_encodings

        if len(all_encodings) == 0:
            # this is the first face
            self.unknown_faces.append(face)
            return

        # see if the face is a match for the previous faces
        distances = face_recognition.face_distance(all_encodings, face.encoding)
        index = np.argmin(distances)
        min_value = distances[index]
        if min_value < self.similarity_threshold:
            # two faces are similar
            if index < len(self.known_persons):
                # face of known person
                self.known_persons[index].add_face(face)
            else:
                # create new person with two faces
                person = Person()
                person.add_face(face)
                newly_known_index = index - len(self.known_persons)
                newly_known_face = self.unknown_faces.pop(newly_known_index)
                person.add_face(newly_known_face)
                self.known_persons.append(person)
        else:
            # unknown face
            self.unknown_faces.append(face)


if __name__ == '__main__':
    import argparse
    import signal
    import os
    import cv2
    import time
    import imutils

    ap = argparse.ArgumentParser()
    ap.add_argument("-e", "--encode", required=True,
                    help="video file to encode or '0' to encode web cam")
    ap.add_argument("-t", "--threshold", default=0.55, type=float,
                    help="threshold of the similarity")
    ap.add_argument("-c", "--capture", default=1, type=int,
                    help="# of frame to capture per second")
    ap.add_argument("-s", "--stop", default=0, type=int,
                    help="stop encoding after # seconds")
    args = ap.parse_args()

    src_file = args.encode
    if src_file == "0":
        src_file = 0

    src = cv2.VideoCapture(src_file)
    if not src.isOpened():
        print("cannot open file", src_file)
        exit(1)

    frame_id = 0
    frame_rate = src.get(5)
    frames_between_capture = int(round(frame_rate) / args.capture)

    print("start detecting from src: %dx%d, %f frame/sec" % (src.get(3), src.get(4), frame_rate))
    print(" - capture every %d frame" % frames_between_capture)
    if args.stop > 0:
        print(" - stop after %d seconds" % args.stop)

    running = True

    def signal_handler(sig, frame):
        print(" stop running...")
        global running
        running = False

    # set SIGINT (^C) handler
    prev_handler = signal.signal(signal.SIGINT, signal_handler)
    print("press ^C to stop detecting immediately")

    fc = FaceClassifier(args.threshold)
    while running:
        ret, frame = src.read()
        if frame is None:
            break

        frame_id += 1
        if frame_id % frames_between_capture != 0:
            continue

        seconds = round(frame_id / frame_rate, 3)
        if args.stop > 0 and seconds > args.stop:
            break

        print()
        print("frame", frame_id, "@", seconds, "seconds")
        start_time = time.time()
        faces = fc.detect_faces(seconds, frame)
        if len(faces) > 0:
            for face in faces:
                fc.classify_face(face)
            s = "%d faces in the frame" % len(faces)
            s += " - %d persons" % len(fc.known_persons)
            s += ", %d unknown faces" % len(fc.unknown_faces)
            print(s)
        elapsed_time = time.time() - start_time
        s = "Operation took %f seconds" % elapsed_time
        print(s)

    # restore SIGINT (^C) handler
    signal.signal(signal.SIGINT, prev_handler)
    running = False
    src.release()
    print()
    print("similarity shreshold:", fc.similarity_threshold)
    print("total", len(fc.known_persons), "persons")
    print("total", len(fc.unknown_faces), "unknown faces")

    # save the results
    os.system("rm -rf unknown*")
    os.system("rm -rf doe*")
    os.system("rm -rf montage*")

    for person in fc.known_persons:
        dir_name = person.name
        os.mkdir(dir_name)
        for face in person.faces:
            filename = str(face.second) + ".jpg"
            pathname = os.path.join(dir_name, filename)
            cv2.imwrite(pathname, face.image)
        images = [face.image for face in person.faces]
        montages = imutils.build_montages(images, (128, 128), (8, 8))
        for i, montage in enumerate(montages):
            filename = "montage." + person.name + ("-%02d.jpg" % i)
            cv2.imwrite(filename, montage)

    if len(fc.unknown_faces) > 0:
        dir_name = "unknown_faces"
        os.mkdir(dir_name)
        i = 0
        for face in fc.unknown_faces:
            i += 1
            filename = str(i) + "-" + str(face.second) + ".jpg"
            pathname = os.path.join(dir_name, filename)
            cv2.imwrite(pathname, face.image)
        images = [face.image for face in fc.unknown_faces]
        montages = imutils.build_montages(images, (128, 128), (8, 8))
        for i, montage in enumerate(montages):
            filename = "montage.unknown_faces-%02d.jpg" % i
            cv2.imwrite(filename, montage)

    # check the result
    if len(fc.known_persons) > 0:
        print()
        print("similarities of persons:")
        encodings = [person.encoding for person in fc.known_persons]
        for person in fc.known_persons:
            distances = face_recognition.face_distance(encodings, person.encoding)
            print("{:10} [".format(person.name), " ".join(["{:5.3f}".format(x) for x in distances]), "]")

