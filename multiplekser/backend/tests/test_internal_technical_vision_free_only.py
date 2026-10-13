"""Offline tests: Technical Vision mirrors all free-key Multiplexer vision models."""
import asyncio
import io
import os
import unittest
from unittest.mock import patch

from fastapi import HTTPException, UploadFile
from starlette.datastructures import Headers

import app.internal_technical_vision as vision
from app.modules.ocr.chain import default_ocr_chain, classify_ocr_chain

FREE_MODELS=(
    "gemini-3.5-flash-lite",
    "gemini-3-flash-preview",
    "gemini-3.1-flash-lite",
    "gemini-3.5-flash",
    "gemini-3.6-flash",
)

class FreeOnlyVisionTests(unittest.TestCase):
    def request(self,fail_first=0,free_key="FREE_TEST",failure_code=429):
        calls=[]
        class Provider:
            async def recognize(self, *, files, model, api_key, prompt, thinking_level):
                calls.append((model,api_key))
                if len(calls)<=fail_first:
                    raise vision.OCRProviderError(
                        f"API {failure_code} unavailable test",status_code=failure_code)
                return '{"result":"test"}'
        upload=UploadFile(file=io.BytesIO(b"nonemptyimage"),
                          filename="photo.jpg",
                          headers=Headers({"content-type":"image/jpeg"}))
        with patch.dict(os.environ,{
            "GEMINI_API_KEY_FREE":free_key,
            "GEMINI_API_KEY_PAID":"PAID_MUST_NEVER_BE_USED",
        }):
            with patch.object(vision,"GeminiProvider",return_value=Provider()):
                try:
                    return asyncio.run(vision._read_with_prompt([upload],"test prompt")),calls
                except HTTPException as exc:
                    return exc,calls

    def test_exact_free_models_are_multiplexer_existing_models(self):
        main=[x.model for x in default_ocr_chain()
              if "klucz darmowy" in x.label]
        classification=[x.model for x in classify_ocr_chain()
                        if "klucz darmowy" in x.label]
        expected=list(dict.fromkeys(main+classification))
        self.assertEqual(tuple(expected),FREE_MODELS)

    def test_primary_fast_flash_lite(self):
        response,calls=self.request()
        self.assertEqual(calls,[(FREE_MODELS[0],"FREE_TEST")])
        self.assertEqual(response["model"],FREE_MODELS[0])

    def test_fallback_every_free_model_in_multiplexer_order(self):
        for fail_first in range(1,5):
            with self.subTest(fail_first=fail_first):
                response,calls=self.request(fail_first=fail_first)
                self.assertEqual([m for m,_ in calls],list(FREE_MODELS[:fail_first+1]))
                self.assertEqual(response["model"],FREE_MODELS[fail_first])
                self.assertEqual({key for _,key in calls},{"FREE_TEST"})

    def test_all_five_free_models_unavailable_429_fails_closed(self):
        result,calls=self.request(fail_first=5)
        self.assertEqual(result.status_code,502)
        self.assertEqual([m for m,_ in calls],list(FREE_MODELS))
        self.assertEqual({key for _,key in calls},{"FREE_TEST"})

    def test_all_five_free_models_unavailable_503_fails_closed(self):
        result,calls=self.request(fail_first=5,failure_code=503)
        self.assertEqual(result.status_code,502)
        self.assertEqual([m for m,_ in calls],list(FREE_MODELS))

    def test_only_paid_key_available_never_calls_any_model(self):
        response,calls=self.request(free_key="")
        self.assertEqual(response.status_code,502)
        self.assertEqual(calls,[])

if __name__=="__main__":
    unittest.main()
