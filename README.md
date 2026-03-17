# Legrand RF Lighting Control

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://hacs.xyz)

A [Home Assistant](https://www.home-assistant.io/) custom integration for the **Legrand LC7001 Whole House Lighting Controller**.

Control your Legrand RF light switches and dimmers directly from Home Assistant — entirely over your **local network**, with **no cloud dependency**.

---

## What You Need

- A **Legrand LC7001** hub ([product page](https://www.legrand.us/wiring-devices/electrical-accessories/miscellaneous/adorne-hub/p/lc7001)), connected to your local network
- **Home Assistant** 2024.1 or newer
- The LC7001's **IP address** (see [Finding Your Hub's IP Address](#finding-your-hubs-ip-address) below)
- The hub's **local password**, if you've set one (most people haven't)

---

## What You Get

Once installed, every light zone configured on your LC7001 appears as a Home Assistant light entity:

- **Switches** — on/off control
- **Dimmers** — on/off, brightness slider, and transition/fade support
- **Real-time updates** — when someone uses a physical switch, Home Assistant updates instantly
- **Diagnostic sensors** — zone count, time zone, DST status, location, and add-a-light mode on the hub device

---

## Installation

### Option 1: HACS (Recommended)

[HACS](https://hacs.xyz/) is the Home Assistant Community Store — a one-click way to install and update custom integrations.

1. Make sure HACS is installed. If not, follow the [HACS installation guide](https://hacs.xyz/docs/use/).
2. In Home Assistant, go to **HACS** → **Integrations**.
3. Click the **⋮** menu (top right) → **Custom repositories**.
4. Paste this URL: `https://github.com/MichaelB2018/legrand_rflc`
5. Set the category to **Integration** and click **Add**.
6. Search for **Legrand RF Lighting Control** and click **Install**.
7. **Restart Home Assistant** (Settings → System → Restart).

After the restart, continue to [Configuration](#configuration) below.

### Option 2: Manual Installation

Use this if you don't have HACS or prefer to manage files yourself.

1. **Download** the latest release from [GitHub](https://github.com/MichaelB2018/legrand_rflc/releases), or clone/download the repository.

2. **Locate your Home Assistant config directory.** This is the folder that contains your `configuration.yaml` file. Common locations:
   - **Home Assistant OS / Supervised**: `/config/`
   - **Docker**: The volume you mounted as `/config`
   - **Core (venv)**: `~/.homeassistant/`

3. **Create the folder** `custom_components/legrand_rflc/` inside your config directory, if it doesn't already exist:
   ```
   config/
   └── custom_components/
       └── legrand_rflc/
   ```

4. **Copy all integration files** into that folder. When done, it should look like this:
   ```
   config/
   └── custom_components/
       └── legrand_rflc/
           ├── __init__.py
           ├── config_flow.py
           ├── const.py
           ├── diagnostics.py
           ├── hub.py
           ├── icons.json
           ├── light.py
           ├── sensor.py
           ├── manifest.json
           ├── strings.json
           ├── quality_scale.yaml
           ├── py.typed
           ├── icon.png
           ├── icon@2x.png
           ├── logo.png
           └── translations/
               └── en.json
   ```

   > **Tip:** You don't need to copy `tests/`, `conftest.py`, `README.md`, `LICENSE`, `hacs.json`, or `.gitignore` — those are development files.

5. **Restart Home Assistant** (Settings → System → Restart).

After the restart, continue to [Configuration](#configuration) below.

---

## Configuration

### Step 1: Find the Integration

1. Go to **Settings** → **Devices & Services**.
2. Click **+ Add Integration** (bottom right).
3. Search for **Legrand RF Lighting Control**.

> **Tip:** If it doesn't appear, make sure you restarted Home Assistant after installation.

### Step 2: Enter Your Hub Details

You'll see a form with two fields:

| Field | What to Enter |
|-------|---------------|
| **Host** | The IP address of your LC7001 hub (e.g., `192.168.1.50`). See below for how to find it. |
| **Password** | The local password, if you've set one on the hub. **Leave blank if you haven't set a password** (this is the default). |

Click **Submit**. The integration will test the connection. If everything works, your lights will appear within a few seconds.

### Step 3: Check Your Devices

Go to **Settings** → **Devices & Services** → **Legrand RF Lighting Control**. You should see:

- **1 hub device** ("Whole House Lighting Controller") with diagnostic sensors
- **1 device per light zone** — each with a light entity you can control

All your lights are now available in dashboards, automations, and scripts.

---

## Finding Your Hub's IP Address

The LC7001 connects to your network via Ethernet. Here are some ways to find its IP:

1. **Check your router's admin page** — look for a device called "Legrand LC7001" or similar in the DHCP client list.
2. **Use the Legrand RFLC app** — the app displays the hub's network info.
3. **Try the default hostname** — `LCM1.local` works on some networks, but **not reliably in Docker** (mDNS doesn't work in most container setups). A static IP is strongly recommended.

> **Recommendation:** Assign a **static IP** (or a DHCP reservation) to your LC7001 in your router settings. This prevents the IP from changing and breaking the integration.

---

## Updating the Integration

### With HACS

HACS will notify you when a new version is available. Click **Update** and restart Home Assistant.

### Manual

Download the new version, replace all files in `custom_components/legrand_rflc/`, and restart Home Assistant.

---

## Changing Settings After Setup

### Change the Hub IP Address

If your hub's IP address changes:

1. Go to **Settings** → **Devices & Services** → **Legrand RF Lighting Control**.
2. Click **⋮** → **Reconfigure**.
3. Enter the new IP and click **Submit**.

### Change the Password

If you change the password on your LC7001:

- Home Assistant will detect the authentication failure and prompt you to **re-authenticate**.
- Enter the new password when prompted.

---

## Removing the Integration

1. Go to **Settings** → **Devices & Services**.
2. Click **Legrand RF Lighting Control**.
3. Click **⋮** → **Delete**.
4. (Optional) Delete the `custom_components/legrand_rflc/` folder if you installed manually.

---

## Troubleshooting

| Problem | What to Do |
|---------|------------|
| **Integration doesn't appear after install** | Make sure you restarted Home Assistant. Check that the files are in `custom_components/legrand_rflc/` (not a subfolder like `custom_components/legrand_rflc/legrand_rflc/`). |
| **"Invalid host" error** | The hub is unreachable. Check that the IP is correct, the hub is powered on, and both devices are on the same network. |
| **"Invalid authentication" error** | The password is wrong. Make sure it matches the password set on the LC7001. If you haven't set one, leave the password field blank. |
| **`LCM1.local` doesn't work** | mDNS (`.local` names) often fails inside Docker containers. Use the hub's IP address instead. |
| **Lights show as "Unavailable"** | The hub is disconnected or unauthenticated. Check the hub's power and network connection. The integration will reconnect automatically when the hub comes back. |
| **New zones not showing up** | Adding or removing zones on the hub triggers an automatic reload. If they don't appear, go to the integration and click **⋮** → **Reload**. |
| **DHCP auto-discovery not working** | On Linux, the HA process needs `cap_net_raw` capability or must run as root. This doesn't affect manual setup. |

---

## Credits

This integration builds on the work of several contributors:

- **[@rtyle](https://github.com/rtyle)** — Original author of the [Home Assistant component](https://github.com/rtyle/home-assistant.core/tree/legrand_rflc) and the [`lc7001`](https://github.com/rtyle/lc7001) Python library (vendored as `hub.py`, MIT license)
- **[@akhudek](https://github.com/akhudek)** — Original HACS packaging and device registry support
- **[@MichaelB2018](https://github.com/MichaelB2018)** — Platinum quality upgrade, sensor platform, ongoing maintenance

## License

[MIT](LICENSE)
