# Build and publish firmware to the controller.
#
#   make sync-config  regenerate libastromech's config header if config/ changed
#   make build      sync-config, bump-version, then pio run (both envs)
#   make bump-version  bump PATCH in version/<env>.txt for envs whose sources changed
#   make package    build, then collect versioned images in dist/
#   make install    package, then copy dist/ to the controller (needs install.conf)
#   make clean
#
# PATCH is bumped automatically when an env's sources changed (BUMP=0 to skip);
# edit version/droid.txt or version/beacon.txt by hand for MINOR/MAJOR. An
# existing role/version is never overwritten (FORCE=1 to override).

-include install.conf

PIO      ?= pio
PYTHON   ?= python3
FIRMWARE_DIR ?= /var/lib/astromech-controller/firmware
FORCE_FLAG = $(if $(FORCE),--force,)
# The sibling libastromech checkout; its top-level config/ (droids, personalities)
# is compiled into the firmware via a generated header.
LIBASTROMECH ?= ../../libastromech

.PHONY: sync-config bump-version build package install clean

# Firmware only knows the personalities in libastromech's generated
# astromech_config.h, so a new/edited YAML has no effect until it is synced.
# pio itself rebuilds whatever the regenerated header touches.
sync-config:
	@$(MAKE) --no-print-directory -C $(LIBASTROMECH) PYTHON=$(PYTHON) check-config >/dev/null 2>&1 \
	  || { echo "libastromech config changed: syncing"; \
	       $(MAKE) --no-print-directory -C $(LIBASTROMECH) PYTHON=$(PYTHON) sync-config; }

# Must follow sync-config so a regenerated header counts as a source change.
bump-version: sync-config
	$(if $(filter 0,$(BUMP)),@echo "BUMP=0: version unchanged",$(PYTHON) scripts/bump_version.py)

build: bump-version
	$(PIO) run

package: build
	$(PYTHON) scripts/package.py $(FORCE_FLAG)

install: package
	@test -n "$(CONTROLLER_HOST)" || { echo "CONTROLLER_HOST unset: copy install.conf.example to install.conf"; exit 1; }
	rsync -rlt --chmod=D755,F644 dist/ $(CONTROLLER_USER:%=%@)$(CONTROLLER_HOST):$(FIRMWARE_DIR)/
	@echo "Installed. Use 'Scan for new firmware' in the controller UI."

clean:
	rm -rf dist
	$(PIO) run -t clean
