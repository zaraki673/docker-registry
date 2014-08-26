# -*- coding: utf-8 -*-

import logging
import logging.handlers
import os
import platform
import sys

from . import toolkit
from .lib import config
from .server import __version__
import flask
from flask.ext.cors import CORS

# configure logging prior to subsequent imports which assume
# logging has been configured
cfg = config.load()
logging.basicConfig(format='%(asctime)s %(levelname)s: %(message)s',
                    level=getattr(logging, cfg.loglevel.upper()),
                    datefmt="%d/%b/%Y:%H:%M:%S %z")

from .lib import mirroring  # noqa

app = flask.Flask('docker-registry')


@app.route('/_ping')
@app.route('/v1/_ping')
def ping():
    headers = {
        'X-Docker-Registry-Standalone': 'mirror' if mirroring.is_mirror()
                                        else (cfg.standalone is True)
    }
    infos = {}
    if cfg.debug:
        # Versions
        versions = infos['versions'] = {}
        headers['X-Docker-Registry-Config'] = cfg.flavor

        for name, module in sys.modules.items():
            if name.startswith('_'):
                continue
            try:
                version = module.__version__
            except AttributeError:
                continue
            versions[name] = version
        versions['python'] = sys.version

        # Hosts infos
        infos['host'] = platform.uname()
        infos['launch'] = sys.argv

    return toolkit.response(infos, headers=headers)


@app.route('/')
def root():
    return toolkit.response(cfg.issue)


def bugsnag(application, api_key, flavor, version):
    # Configure bugsnag
    if api_key:
        import bugsnag
        import bugsnag.flask

        root_path = os.path.abspath(os.path.dirname(os.path.dirname(__file__)))
        bugsnag.configure(api_key=api_key,
                          project_root=root_path,
                          release_stage=flavor,
                          notify_release_stages=[flavor],
                          app_version=version
                          )
        bugsnag.flask.handle_exceptions(application)


def init():
    # Configure the email exceptions
    info = cfg.email_exceptions
    if info and info.smtp_host:
        mailhost = info.smtp_host
        mailport = info.smtp_port
        if mailport:
            mailhost = (mailhost, mailport)
        smtp_secure = info.smtp_secure
        secure_args = _adapt_smtp_secure(smtp_secure)
        mail_handler = logging.handlers.SMTPHandler(
            mailhost=mailhost,
            fromaddr=info.from_addr,
            toaddrs=[info.to_addr],
            subject='Docker registry exception',
            credentials=(info.smtp_login,
                         info.smtp_password),
            secure=secure_args)
        mail_handler.setLevel(logging.ERROR)
        app.logger.addHandler(mail_handler)
    bugsnag(app, cfg.bugsnag, cfg.flavor, __version__)
    # Configure flask_cors
    for i in cfg.cors.keys():
        app.config['CORS_%s' % i.upper()] = cfg.cors[i]
    CORS(app)


def _adapt_smtp_secure(value):
    """Adapt the value to arguments of ``SMTP.starttls()``

    .. seealso:: <http://docs.python.org/2/library/smtplib.html\
#smtplib.SMTP.starttls>

    """
    if isinstance(value, basestring):
        # a string - wrap it in the tuple
        return (value,)
    if isinstance(value, config.Config):
        assert set(value.keys()) <= set(['keyfile', 'certfile'])
        return (value.keyfile, value.certfile)
    if value:
        return ()


init()
