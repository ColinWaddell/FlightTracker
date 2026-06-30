from time import perf_counter, sleep

DELAY_DEFAULT = 0.01


class Animator(object):
    class KeyFrame(object):
        @staticmethod
        def add(divisor, offset=0):
            def wrapper(func):
                func.properties = {"divisor": divisor, "offset": offset, "count": 0}
                return func

            return wrapper

    def __init__(self):
        self.keyframes = []
        self.frame = 0
        self.delay_value = DELAY_DEFAULT
        self.reset_scene_flag = True

        self.register_keyframes()

        super().__init__()

    def register_keyframes(self):
        # Some introspection to setup keyframes
        for methodname in dir(self):
            method = getattr(self, methodname)
            if hasattr(method, "properties"):
                self.keyframes.append(method)

    def reset_scene(self):
        for keyframe in self.keyframes:
            if keyframe.properties["divisor"] == 0:
                keyframe()

    def play(self):
        while True:
            start_time = perf_counter()

            for keyframe in self.keyframes:
                # If divisor == 0 then only run once on first loop
                if self.frame == 0:
                    if keyframe.properties["divisor"] == 0:
                        keyframe()

                # Otherwise perform normal operation
                if (
                    self.frame > 0
                    and keyframe.properties["divisor"]
                    and not (
                        (self.frame - keyframe.properties["offset"])
                        % keyframe.properties["divisor"]
                    )
                ):
                    if keyframe(keyframe.properties["count"]):
                        keyframe.properties["count"] = 0
                    else:
                        keyframe.properties["count"] += 1

            self.reset_scene_flag = False
            self.frame += 1

            elapsed = perf_counter() - start_time
            target = self.delay_value
            sleep_time = target - elapsed
            if sleep_time < 0.001:
                sleep_time = 0.001
            elif sleep_time > 0.05:
                sleep_time = 0.05
            sleep(sleep_time)

    @property
    def delay(self):
        return self.delay_value

    @delay.setter
    def delay(self, value):
        self.delay_value = value


if __name__ == "__main__":

    class Test(Animator):
        @Animator.KeyFrame.add(5, 1)
        def method1(self, frame):
            print(f"method1 {frame}")

        @Animator.KeyFrame.add(1, 1)
        def method2(self, frame):
            print(f"method2 {frame}")

    myclass = Test(1)
    myclass.run()

    while 1:
        sleep(5)
