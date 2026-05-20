from functools import wraps


def persistence(func, static, dynamic):
    """decorator for handling persistence.
    static fields are fields that are set only once in the constructor and
    thus only need to be stored. Dynamic fields are part of the dynamic state
    of the object and are set during restoring in addition to being stored."""
    for entry in static.keys():
        if static[entry] is None:
            static[entry] = lambda that: that.__getattribute__(entry)
    for entry in dynamic.keys():
        if dynamic[entry] is None:
            dynamic[entry] = (
                lambda that: that.__getattribute__(entry),
                lambda that, v: that.__setattr__(entry, v),
            )
        else:
            __getter, __setter = dynamic[entry]
            getter = __getter or (
                lambda that: that.__getattribute__(entry)
            )
            setter = __setter or (
                lambda that, v: that.__setattr__(entry, v)
            )
            dynamic[entry] = (getter, setter)

    @wraps(func)
    def wrapper(this, obj=None):
        if obj is None:  # setter case
            d = dict()
            for entry, f in static.items():
                d[entry] = f(this)
            for entry, (f, _) in dynamic.items():
                d[entry] = f(this)
            return d
        else:  # getter case
            for entry, (_, f) in dynamic.items():
                f(this, obj[entry])

    return wrapper
