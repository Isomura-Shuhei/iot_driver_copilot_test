import os
import asyncio
import json
from aiohttp import web
from aiocoap import *
from aiocoap.numbers.codes import Code

# Environment Variables
LWM2M_SERVER_IP = os.environ.get("LWM2M_SERVER_IP", "127.0.0.1")
LWM2M_SERVER_PORT = int(os.environ.get("LWM2M_SERVER_PORT", 5683))
DEVICE_EPNAME = os.environ.get("DEVICE_EPNAME", "raspi5")
HTTP_SERVER_HOST = os.environ.get("HTTP_SERVER_HOST", "0.0.0.0")
HTTP_SERVER_PORT = int(os.environ.get("HTTP_SERVER_PORT", 8080))
COAP_BIND_PORT = int(os.environ.get("COAP_BIND_PORT", 56830))

# LwM2M/CoAP Resource Paths
LWM2M_OBJECTS = {
    "device_identity": "/3/0",        # Device Object
    "power": "/3/0/7",                # Battery Level
    "memory_free": "/3/0/10",         # Free Memory
    "memory_total": "/3/0/9",         # Total Memory
    "network": "/4/0",                # Connectivity Monitoring
    "firmware_state": "/5/0/3",       # Firmware State
    "firmware_result": "/5/0/5",      # Firmware Update Result
    "location": "/6/0",               # Location Object
}

# CoAP Endpoint for registration
LWM2M_REG_PATH = "/rd"

# Async LwM2M/CoAP Client
class LwM2MClient:
    def __init__(self, server_ip, server_port, epname, coap_port):
        self.server_ip = server_ip
        self.server_port = server_port
        self.epname = epname
        self.coap_port = coap_port

    async def _get_context(self):
        return await Context.create_client_context(bind=("0.0.0.0", self.coap_port))

    async def register(self, params):
        ctx = await self._get_context()
        payload = b''
        query = [
            f"ep={self.epname}",
            "lt=86400",
            "b=U"
        ]
        # Optionally add objects
        if "objects" in params and isinstance(params["objects"], list):
            objstr = ",".join(params["objects"])
            query.append(f"lwm2m={objstr}")
        uri = f"coap://{self.server_ip}:{self.server_port}{LWM2M_REG_PATH}"
        req = Message(code=POST, uri=uri, uri_query=query, payload=payload)
        resp = await ctx.request(req).response
        return resp

    async def execute_command(self, command):
        ctx = await self._get_context()
        if command == "reboot":
            path = "/3/0/4"
        elif command == "factory_reset":
            path = "/3/0/5"
        elif command == "firmware_update":
            path = "/5/0/2"
        else:
            raise Exception("Unknown command")
        uri = f"coap://{self.server_ip}:{self.server_port}{path}"
        req = Message(code=POST, uri=uri)
        resp = await ctx.request(req).response
        return resp

    async def get_device_info(self):
        ctx = await self._get_context()
        devobj = LWM2M_OBJECTS["device_identity"]
        mem_obj = LWM2M_OBJECTS["memory_free"]
        mem_total_obj = LWM2M_OBJECTS["memory_total"]
        net_obj = LWM2M_OBJECTS["network"]
        fw_state_obj = LWM2M_OBJECTS["firmware_state"]
        fw_result_obj = LWM2M_OBJECTS["firmware_result"]
        location_obj = LWM2M_OBJECTS["location"]

        async def safe_get(path):
            try:
                uri = f"coap://{self.server_ip}:{self.server_port}{path}"
                req = Message(code=GET, uri=uri)
                resp = await ctx.request(req).response
                return resp.payload.decode(errors="ignore")
            except Exception:
                return None

        identity = await safe_get(devobj)
        memory_free = await safe_get(mem_obj)
        memory_total = await safe_get(mem_total_obj)
        network = await safe_get(net_obj)
        fw_state = await safe_get(fw_state_obj)
        fw_result = await safe_get(fw_result_obj)
        location = await safe_get(location_obj)

        return {
            "identity": identity,
            "memory_free": memory_free,
            "memory_total": memory_total,
            "network": network,
            "firmware_state": fw_state,
            "firmware_update_result": fw_result,
            "location": location
        }

# HTTP API Handlers
lwm2m_client = LwM2MClient(LWM2M_SERVER_IP, LWM2M_SERVER_PORT, DEVICE_EPNAME, COAP_BIND_PORT)

async def reg_handler(request):
    try:
        data = await request.json()
    except Exception:
        data = {}
    try:
        resp = await lwm2m_client.register(data)
        return web.json_response({
            "result": "registered",
            "code": resp.code.name,
            "location": resp.opt.location_path if hasattr(resp.opt, "location_path") else "",
            "payload": resp.payload.decode(errors="ignore")
        })
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)

async def cmd_handler(request):
    try:
        data = await request.json()
        command = data.get("command")
        if not command:
            return web.json_response({"error": "Missing command parameter"}, status=400)
        resp = await lwm2m_client.execute_command(command)
        return web.json_response({
            "result": "executed",
            "code": resp.code.name,
            "payload": resp.payload.decode(errors="ignore")
        })
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)

async def info_handler(request):
    try:
        info = await lwm2m_client.get_device_info()
        return web.json_response(info)
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)

# HTTP Server Setup
def main():
    app = web.Application()
    app.router.add_post('/reg', reg_handler)
    app.router.add_post('/cmd', cmd_handler)
    app.router.add_get('/info', info_handler)
    web.run_app(app, host=HTTP_SERVER_HOST, port=HTTP_SERVER_PORT)

if __name__ == "__main__":
    main()