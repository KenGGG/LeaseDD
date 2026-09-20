import os
from .app import create_app
app=create_app(initialize=False,secure_cookie=os.getenv('LEASEDD_SECURE_COOKIE','true')=='true')
