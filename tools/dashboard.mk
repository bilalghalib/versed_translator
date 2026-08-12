# tools/dashboard.mk
#
# Standalone make target for the status dashboard. Not wired into the main
# Makefile on purpose (owned by another agent) — invoke explicitly:
#
#   make -f tools/dashboard.mk dashboard
#
.PHONY: dashboard

dashboard:
	python3 tools/build_dashboard.py
