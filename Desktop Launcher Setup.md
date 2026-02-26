### Desktop Launcher Setup

To create a clickable desktop shortcut for launching the application with the correct
working directory and Conda environment, follow the steps below.

#### 1. Create a wrapper script

Create the file:


~/Nextcloud/Bezahlkarte_Gutscheine/voucher-scanner/start_voucher_scanner.sh


with the following content:

```bash
#!/usr/bin/env bash
cd "$(dirname "$0")"

# Initialise conda
source ~/miniconda3/etc/profile.d/conda.sh
conda activate voucher-scanner

python voucher-scanner.py

Make it executable:

chmod +x ~/Nextcloud/Bezahlkarte_Gutscheine/voucher-scanner/start_voucher_scanner.sh
2. Create a desktop entry

Create the file:

~/.local/share/applications/start_voucher_scanner.desktop

with the following content:

[Desktop Entry]
Type=Application
Name=Start Voucher Scanner
Exec=/home/<USER>/Nextcloud/Bezahlkarte_Gutscheine/voucher-scanner/start_voucher_scanner.sh
Icon=/home/<USER>/Nextcloud/Bezahlkarte_Gutscheine/voucher-scanner/icon.png
Terminal=true

Replace <USER> with your username.

Set permissions and update the desktop database:

chmod 755 ~/.local/share/applications/start_voucher_scanner.desktop
update-desktop-database ~/.local/share/applications/
3. Create a desktop link (optional)

To place a clickable launcher on the desktop:

ln -s ~/.local/share/applications/start_voucher_scanner.desktop ~/Desktop/

or use 
ln -s ~/.local/share/applications/start_voucher_scanner.desktop ~/Schreibtisch/

On GNOME, right-click the desktop entry and enable Allow Launching.

This launcher will open the voucher-scanner application in the correct directory and environment.
