import pygame
from obswebsocket import obsws, requests
from onvif import ONVIFCamera
from dotenv import load_dotenv
import os
import time
import json

PRESETS_FILE = "presets.json"
manual_control_enabled = True
# Загрузка .env
load_dotenv()

# Настройки
ptz_speed = float(os.getenv("PTZ_SPEED", 0.5))
zoom_speed = float(os.getenv("ZOOM_SPEED", 0.5))

# OBS параметры
OBS_HOST = os.getenv("OBS_HOST")
OBS_PORT = int(os.getenv("OBS_PORT"))
OBS_PASSWORD = os.getenv("OBS_PASSWORD")

# Камеры ONVIF
cameras = [
    {
        'ip': os.getenv("CAM1_IP"),
        'port': int(os.getenv("CAM1_PORT")),
        'user': os.getenv("CAM1_USER"),
        'pass': os.getenv("CAM1_PASS")
    },
    {
        'ip': os.getenv("CAM2_IP"),
        'port': int(os.getenv("CAM2_PORT")),
        'user': os.getenv("CAM2_USER"),
        'pass': os.getenv("CAM2_PASS")
    }
]

current_camera_index = 0

def initialize_camera(index):
    global camera, media_service, ptz_service, media_profile, token
    cam = cameras[index]
    camera = ONVIFCamera(cam['ip'], cam['port'], cam['user'], cam['pass'])
    media_service = camera.create_media_service()
    ptz_service = camera.create_ptz_service()
    media_profile = media_service.GetProfiles()[0]
    token = media_profile.token
    print(f"📷 Подключено к камере {index + 1}: {cam['ip']}")

initialize_camera(current_camera_index)

# OBS подключение
ws = obsws(OBS_HOST, OBS_PORT, OBS_PASSWORD)
try:
    ws.connect()
    scenes_response = ws.call(requests.GetSceneList())
    scenes = [scene['sceneName'] for scene in scenes_response.getScenes()]
    scenes.reverse()
    print("✅ Подключено к OBS")
    print(f"Сцены: {scenes}")
except Exception as e:
    print(f"❌ Ошибка подключения к OBS: {e}")

# Инициализация Pygame и джойстиков
pygame.init()
pygame.joystick.init()

joysticks = {}
for i in range(pygame.joystick.get_count()):
    js = pygame.joystick.Joystick(i)
    js.init()
    joysticks[i] = js
    print(f"🎮 Геймпад {i}: {js.get_name()}")

def save_preset(camera_index, ptz_position):
    try:
        with open(PRESETS_FILE, "r") as f:
            presets = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        presets = {}

    presets[str(camera_index)] = ptz_position

    with open(PRESETS_FILE, "w") as f:
        json.dump(presets, f, indent=4)

    print(f"💾 Пресет сохранён для камеры {camera_index + 1}")

def load_preset(camera_index):
    try:
        with open(PRESETS_FILE, "r") as f:
            presets = json.load(f)
        return presets.get(str(camera_index), None)
    except (FileNotFoundError, json.JSONDecodeError):
        return None

def move_to_preset(preset):
    global manual_control_enabled
    if not preset:
        print("❌ Пресет не найден.")
        return

    manual_control_enabled = False

    request = ptz_service.create_type('AbsoluteMove')
    request.ProfileToken = token
    request.Position = {
        'PanTilt': {
            'x': preset['pan'],
            'y': preset['tilt']
        },
        'Zoom': {
            'x': preset['zoom']
        }
    }

    # 🔥 Максимальная скорость (1.0 = максимум для PanTilt и Zoom)
    request.Speed = {
        'PanTilt': {'x': 1.0, 'y': 1.0},
        'Zoom': {'x': 1.0}
    }

    ptz_service.AbsoluteMove(request)
    print("📍 Переход к пресету на максимальной скорости...")

    time.sleep(2)
    manual_control_enabled = True



def move_camera(pan, tilt, zoom):
    request = ptz_service.create_type('ContinuousMove')
    request.ProfileToken = token
    request.Velocity = {
        'PanTilt': {'x': pan, 'y': tilt},
        'Zoom': {'x': zoom}
    }
    ptz_service.ContinuousMove(request)

def stop_camera():
    request = ptz_service.create_type('Stop')
    request.ProfileToken = token
    request.PanTilt = True
    request.Zoom = True
    ptz_service.Stop(request)

# Главный цикл
try:
    while True:
        pygame.event.pump()
        for event in pygame.event.get():
            if event.type == pygame.JOYBUTTONDOWN:
                joy_id = event.joy
                button = event.button
                print(f"[{joy_id}] Кнопка {button} нажата")

                # Левый Joy-Con: переключение сцен и настройка скорости
                if joy_id == 0:
                    if button == 0:
                        ws.call(requests.SetCurrentProgramScene(sceneName=scenes[0]))
                    elif button == 1:
                        ws.call(requests.SetCurrentProgramScene(sceneName=scenes[1]))
                    elif button == 2:
                        ws.call(requests.SetCurrentProgramScene(sceneName=scenes[2]))
                    elif button == 3:
                        ws.call(requests.SetCurrentProgramScene(sceneName=scenes[3]))
                    elif button == 14:
                        ptz_speed = max(0.1, ptz_speed - 0.1)
                        print(f"🔽 Скорость PTZ уменьшена: {ptz_speed}")
                    elif button == 15:
                        ptz_speed = min(1.0, ptz_speed + 0.1)
                        print(f"🔼 Скорость PTZ увеличена: {ptz_speed}")

                # Правый Joy-Con: переключение камер
                elif joy_id == 1:
                    if button == 0:
                        current_camera_index = 0
                        initialize_camera(current_camera_index)
                    elif button == 1:
                        current_camera_index = 1
                        initialize_camera(current_camera_index)
                    elif button == 2:
                        status = ptz_service.GetStatus({'ProfileToken': token})
                        pan = status.Position.PanTilt.x
                        tilt = status.Position.PanTilt.y
                        zoom = status.Position.Zoom.x
                        save_preset(current_camera_index, {'pan': pan, 'tilt': tilt, 'zoom': zoom})
                    elif button == 3:
                        preset = load_preset(current_camera_index)
                        move_to_preset(preset)
                    elif button == 14:
                        zoom_speed = max(0.1, zoom_speed- 0.1)
                        print(f"🔽 Скорость Zoom уменьшена: {zoom_speed}")
                    elif button == 15:
                        zoom_speed = min(1.0, zoom_speed + 0.1)
                        print(f"🔼 Скорость Zoom увеличена: {zoom_speed}")

            elif event.type == pygame.JOYHATMOTION:
                joy_id = event.joy
                x, y = event.value
                print(f"[{joy_id}] HAT: ({x}, {y})")

        if manual_control_enabled:
            # Управление движением камеры (левый джойкон)
            tilt, pan = joysticks[0].get_hat(0)
            pan *= ptz_speed
            tilt *= ptz_speed

            # Управление зумом (правый джойкон)
            zoom_dir, _ = joysticks[1].get_hat(0)
            zoom = zoom_dir * zoom_speed

            if pan != 0 or tilt != 0 or zoom != 0:
                move_camera(pan, -tilt, zoom)
            else:
                stop_camera()

        time.sleep(0.01)

except KeyboardInterrupt:
    stop_camera()
    print("\n🚪 Выход")
