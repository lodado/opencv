#!/usr/bin/env python3

from person import Person
from person import Face
from person import PersonDB
import face_recognition
import numpy as np
from datetime import datetime


class FaceClassifier():
    def __init__(self, threshold):
        self.similarity_threshold = threshold

    def get_face_image(self, frame, box):
        img_height, img_width = frame.shape[:2]
        (box_top, box_right, box_bottom, box_left) = box
        box_width = box_right - box_left
        box_height = box_bottom - box_top
        crop_top = max(box_top - box_height, 0)
        pad_top = -min(box_top - box_height, 0)
        crop_bottom = min(box_bottom + box_height, img_height - 1)
        pad_bottom = max(box_bottom + box_height - img_height, 0)
        crop_left = max(box_left - box_width, 0)
        pad_left = -min(box_left - box_width, 0)
        crop_right = min(box_right + box_width, img_width - 1)
        pad_right = max(box_right + box_width - img_width, 0)
        face_image = frame[crop_top:crop_bottom, crop_left:crop_right]
        if (pad_top == 0 and pad_bottom == 0):
            if (pad_left == 0 and pad_right == 0):
                return face_image
        padded = cv2.copyMakeBorder(face_image, pad_top, pad_bottom,
                                    pad_left, pad_right, cv2.BORDER_CONSTANT)
        return padded

    def detect_faces(self, frame):
        faces = []
        rgb = frame[:, :, ::-1]
        boxes = face_recognition.face_locations(rgb, model="hog")
        if not boxes:
            return faces

        # faces found
        now = datetime.now()
        str_ms = now.strftime('%Y%m%d_%H%M%S.%f')[:-3] + '-'
        encodings = face_recognition.face_encodings(rgb, boxes)
        for i, box in enumerate(boxes):
            face_image = self.get_face_image(frame, box)
            face = Face(str_ms + str(i) + ".png", face_image, encodings[i])
            faces.append(face)
        return faces

    def compare_face(self, face, persons, unknown_faces):
        if len(persons) > 0:
            # see if the face is a match for the faces of known person
            encodings = [person.encoding for person in persons]
            distances = face_recognition.face_distance(encodings, face.encoding)
            index = np.argmin(distances)
            min_value = distances[index]
            if min_value < self.similarity_threshold:
                # face of known person
                persons[index].add_face(face)
                return persons[index]

        if len(unknown_faces) == 0:
            # this is the first face
            unknown_faces.append(face)
            return None

        encodings = [face.encoding for face in unknown_faces]
        distances = face_recognition.face_distance(encodings, face.encoding)
        index = np.argmin(distances)
        min_value = distances[index]
        if min_value < self.similarity_threshold:
            # two faces are similar
            # create new person with two faces
            person = Person()
            newly_known_face = unknown_faces.pop(index)
            person.add_face(newly_known_face)
            person.add_face(face)
            persons.append(person)
            return person
        else:
            # unknown face
            unknown_faces.append(face)
            return None


if __name__ == '__main__':
    import argparse
    import signal
    import cv2
    import time
    import imutils

    ap = argparse.ArgumentParser()
    ap.add_argument("-i", "--input", required=True,
                    help="video file to detect or '0' to detect from web cam")
    ap.add_argument("-c", "--capture", default=1, type=int,
                    help="# of frame to capture per second")
    ap.add_argument("-s", "--stop", default=0, type=int,
                    help="stop detecting after # seconds")
    ap.add_argument("-t", "--threshold", default=0.5, type=float,
                    help="threshold of the similarity")
    args = ap.parse_args()

    src_file = args.input
    if src_file == "0":
        src_file = 0

    src = cv2.VideoCapture(src_file)
    if not src.isOpened():
        print("cannot open input file", src_file)
        exit(1)

    frame_width = src.get(cv2.CAP_PROP_FRAME_WIDTH)
    frame_height = src.get(cv2.CAP_PROP_FRAME_HEIGHT)

    frame_id = 0
    frame_rate = src.get(5)
    frames_between_capture = int(round(frame_rate) / args.capture)
    dir_name = "result"

    print("source", args.input)
    print("%dx%d, %f frame/sec" % (src.get(3), src.get(4), frame_rate))
    print("capture every %d frame" % frames_between_capture)
    print("similarity shreshold:", args.threshold)
    if args.stop > 0:
        print("will stop after %d seconds." % args.stop)

    pdb = PersonDB()
    pdb.load_db(dir_name)
    pdb.print_persons()

    running = True

    # set SIGINT (^C) handler
    def signal_handler(sig, frame):
        global running
        running = False
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

        start_time = time.time()

        # this is main
        faces = fc.detect_faces(frame)
        for face in faces:
            fc.compare_face(face, pdb.persons, pdb.unknown.faces)

        elapsed_time = time.time() - start_time

        s = "\rframe " + str(frame_id)
        s += " @ time %.3f" % seconds
        s += " takes %.3f seconds" % elapsed_time
        s += ", %d new faces" % len(faces)
        s += " -> " + repr(pdb)
        print(s, end="    ")

    # restore SIGINT (^C) handler
    signal.signal(signal.SIGINT, prev_handler)
    running = False
    src.release()
    print()

    pdb.save_db(dir_name)
    pdb.print_persons()
