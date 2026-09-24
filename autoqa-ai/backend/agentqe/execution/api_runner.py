import httpx


class APIRunner:

    def run(
        self,
        method,
        url,
        **kwargs
    ):

        response = httpx.request(
            method,
            url,
            **kwargs
        )

        return {
            "status": (
                "PASS"
                if response.is_success
                else "FAIL"
            ),

            "status_code":
                response.status_code,

            "response":
                response.text[:5000]
        }