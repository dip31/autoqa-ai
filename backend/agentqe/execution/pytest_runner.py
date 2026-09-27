import subprocess
import time


class PytestRunner:

    def run(
        self,
        test_path
    ):

        start = time.time()

        process = subprocess.run(
            [
                "pytest",
                test_path,
                "-q"
            ],
            capture_output=True,
            text=True
        )

        return {
            "status": (
                "PASS"
                if process.returncode == 0
                else "FAIL"
            ),

            "duration":
                time.time() - start,

            "stdout":
                process.stdout,

            "stderr":
                process.stderr
        }