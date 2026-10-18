# GENERATED FILE - run tools/gen.py, do not edit by hand

class Patient:
    __slots__ = ("id", "name", "phone",)
    id: int
    name: str
    phone: str

class Appointment:
    __slots__ = ("id", "patient_id", "at",)
    id: int
    patient_id: int
    at: str
