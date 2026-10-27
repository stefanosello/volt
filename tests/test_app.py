import base64
import io
import os
import tempfile
import unittest
from unittest.mock import patch

import app as volt


class VoltTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        volt.DB = os.path.join(self.tmp.name, 'test.db')
        self.client = volt.app.test_client()
        self.env = patch.dict(os.environ, {'ADMIN_PASSWORD': 'test-pass', 'SECRET_KEY': 'test-secret', 'OPENAI_API_KEY': ''})
        self.env.start()

    def tearDown(self):
        self.env.stop()
        self.tmp.cleanup()

    def test_create_and_review(self):
        response = self.client.post('/requests', data={'service': 'outlet', 'name': 'Alex', 'contact': 'alex@example.com', 'postcode': '31036', 'description': 'Two outlets'}, content_type='multipart/form-data')
        self.assertEqual(response.status_code, 201)
        auth = {'Authorization': 'Basic ' + base64.b64encode(b'admin:test-pass').decode()}
        admin = self.client.get('/admin', headers=auth)
        self.assertIn(b'Two outlets', admin.data)
        with volt.database() as con:
            job = con.execute('SELECT id FROM jobs').fetchone()
        rv = self.client.post(f'/admin/{job[0]}/review', headers=auth, data={'csrf': volt.csrf_for(job[0]), 'price_eur': '120'})
        self.assertEqual(rv.status_code, 302)
        with volt.database() as con:
            self.assertEqual(con.execute('SELECT price_eur FROM jobs').fetchone()[0], 120)

    def test_admin_requires_password(self):
        self.assertEqual(self.client.get('/admin').status_code, 401)

    def test_rejects_invalid_photo(self):
        response = self.client.post('/requests', data={'service': 'outlet', 'name': 'Alex', 'contact': 'alex@example.com', 'postcode': '31036', 'description': 'Two outlets', 'photos': (io.BytesIO(b'not an image'), 'fake.jpg')}, content_type='multipart/form-data')
        self.assertEqual(response.status_code, 400)


if __name__ == '__main__':
    unittest.main()
