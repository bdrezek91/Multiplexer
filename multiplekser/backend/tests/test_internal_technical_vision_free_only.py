"""No-network tests: technical Vision never uses the paid Gemini key."""
import asyncio
import io
import os
import unittest
from unittest.mock import patch

from fastapi import HTTPException, UploadFile
from starlette.datastructures import Headers

import app.internal_technical_vision as vision


class FreeOnlyVisionTests(unittest.TestCase):
    def request(self, failure=None, free_key="FREE_TEST"):
        calls=[]
        class Provider:
            async def recognize(self, *, files, model, api_key, prompt, thinking_level):
                calls.append((model,api_key))
                if failure=="first" and model=="gemini-3.5-flash-lite":
                    raise vision.OCRProviderError("429 test",status_code=429)
                if failure=="all":
                    raise vision.OCRProviderError("503 test",status_code=503)
                return '{"result":"test"}'
        upload=UploadFile(file=io.BytesIO(b"nonemptyimage"),
                          filename="photo.jpg",
                          headers=Headers({"content-type":"image/jpeg"}))
        with patch.dict(os.environ,{"GEMINI_API_KEY_FREE":free_key,
                                    "GEMINI_API_KEY_PAID":"PAID_MUST_NEVER_BE_USED"}):
            with patch.object(vision,"GeminiProvider",return_value=Provider()):
                try:
                    response=asyncio.run(vision._read_with_prompt([upload],"test prompt"))
                    return response,calls
                except HTTPException as e:
                    return e,calls

    def test_primary_is_free_flash_lite(self):
        response,calls=self.request()
        self.assertEqual(calls,[("gemini-3.5-flash-lite","FREE_TEST")])
        self.assertEqual(response["model"],"gemini-3.5-flash-lite")

    def test_rate_limit_fallback_uses_second_free_flash_lite(self):
        response,calls=self.request(failure="first")
        self.assertEqual(calls,[("gemini-3.5-flash-lite","FREE_TEST"),
                                ("gemini-3.1-flash-lite","FREE_TEST")])
        self.assertEqual(response["model"],"gemini-3.1-flash-lite")

    def test_all_free_unavailable_fails_closed_no_paid(self):
        response,calls=self.request(failure="all")
        self.assertEqual(response.status_code,502)
        self.assertEqual(len(calls),2)
        self.assertNotIn("PAID_MUST_NEVER_BE_USED",[key for _,key in calls])

    def test_only_paid_key_available_fails_closed(self):
        response,calls=self.request(free_key="")
        self.assertEqual(response.status_code,502)
        self.assertEqual(calls,[])


if __name__=="__main__":
    unittest.main()
