from utils.bootstrap import bootstrap_application
from utils.config_utils import load_settings
from web.factory import create_app, app_logger

settings = load_settings(force_reload=True)
bootstrap_application(settings)
app = create_app(settings)

if __name__ == "__main__":
    app_logger.info("启动Web管理界面，地址: http://0.0.0.0:8081")
    app.run(debug=False, host="0.0.0.0", port=8081, use_reloader=False)
