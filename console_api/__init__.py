import logging 

from websocket_server import WebsocketServer
from mcdreforged.api.all import *
from mcdreforged.info_reactor.info import InfoSource

from console_api.config import Config

class LimitedList(list):

    def __init__(self, max_size: int):
        self.max_size = max_size
        super().__init__()

    def append(self, object):
        if len(self) >= self.max_size:
            self.pop(0)
        
        super().append(object)

config: Config
goal_server: PluginServerInterface
history: LimitedList
api_server: WebsocketServer

class CustomHandler(logging.StreamHandler):
    def emit(self, record):
        msg = self.format(record)
        
        history.append(msg)
        api_server.send_message_to_all(msg)

def on_load(server: PluginServerInterface, old):
    global config
    global history
    global goal_server
    global api_server

    handler = CustomHandler()
    handler.setFormatter(server._mcdr_server.logger.get_console_formatter(None))

    server._mcdr_server.logger.addHandler(handler)
    
    server.logger.info("Console API is loading...")
    goal_server = server

    config = server.load_config_simple("config.json", in_data_folder=True, target_class=Config)
    Config.set_instance(config)

    history = LimitedList(config.max_line)

    server.register_command(Literal(config.prefix).runs(send_help).then(Literal("state").runs(get_state)))

    server.logger.info(f"Websocket server is running on localhost:{config.port}")

    api_server = WebsocketServer(port=config.port, loglevel=logging.WARN)
    api_server.set_fn_new_client(on_client)
    api_server.set_fn_message_received(on_message)

    start_server()

def is_alive():
    return api_server.thread is not None and api_server.thread.is_alive()

def on_unload(server: PluginServerInterface):
    if is_alive():
        api_server.shutdown()

def on_info(server: PluginServerInterface, info: Info):
    global history
    history.append(info.raw_content)
    
    if is_alive():
        api_server.send_message_to_all(info.raw_content)

@new_thread("Console API Server")
def start_server():
    api_server.run_forever()

def on_message(client, server, message: str):
    if(message.startswith("!!")):
        fake_info = Info()
        fake_info.source = InfoSource.CONSOLE
        goal_server.execute_command(command=message, source=ConsoleCommandSource(goal_server._mcdr_server, fake_info))
    else:
        goal_server.execute(message)

def on_client(client, server:WebsocketServer):
    server.send_message(client, "Receiving...")
    for line in history:
        server.send_message(client, line)

def get_state(src: CommandSource):

    rtexts = [
        RTextList(
            RText("当前状态: "),
            RText("RUNING" if is_alive() else "STOP").set_color(RColor.yellow if is_alive() else RColor.red).set_styles(RStyle.bold)
        ),
        RTextList("端口: ", RText(config.port).set_color(RColor.yellow)),
        RTextList("已记录: ", RText(len(history)).set_color(RColor.yellow))
    ]

    for rtext in rtexts:
        src.reply(rtext)

def send_help(src: CommandSource):
    prefix = config.prefix
    msg = f'''
    ------------§aCommand Useage§r---------------
    | {prefix} - 显示这条帮助命令
    | {prefix} state - 查看API状态
    '''
    src.reply(msg)

