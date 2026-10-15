# SPDX-License-Identifier: BSD-3-Clause
# actuator-lint engine.
#
# Built as a PX4 "external modules" directory, so no file tracked by PX4 is
# modified:
#   cmake -S <PX4> -B <build> -G Ninja -DCONFIG=px4_sitl_default \
#         -DEXTERNAL_MODULES_LOCATION=<this repo>/engine
#   ninja -C <build> actuator_lint_engine
#
# Only the actuator_lint_engine target is built, not the PX4 firmware itself.

if(BUILD_TESTING)
	# PX4's test configuration enables sanitizers and defines the same app-map
	# functions as main.cpp.
	message(FATAL_ERROR "actuator_lint_engine is built with -DCONFIG=px4_sitl_default, not with a test configuration")
endif()

execute_process(
	COMMAND git describe --tags --always --dirty
	WORKING_DIRECTORY ${PX4_SOURCE_DIR}
	OUTPUT_VARIABLE ACTUATOR_LINT_ENGINE_PX4_VERSION
	OUTPUT_STRIP_TRAILING_WHITESPACE
)
execute_process(
	COMMAND git rev-parse HEAD
	WORKING_DIRECTORY ${PX4_SOURCE_DIR}
	OUTPUT_VARIABLE ACTUATOR_LINT_ENGINE_PX4_COMMIT
	OUTPUT_STRIP_TRAILING_WHITESPACE
)

add_executable(actuator_lint_engine EXCLUDE_FROM_ALL main.cpp)

target_compile_definitions(actuator_lint_engine PRIVATE
	MODULE_NAME="actuator_lint_engine"
	ACTUATOR_LINT_ENGINE_PX4_VERSION="${ACTUATOR_LINT_ENGINE_PX4_VERSION}"
	ACTUATOR_LINT_ENGINE_PX4_COMMIT="${ACTUATOR_LINT_ENGINE_PX4_COMMIT}"
)

# ControlAllocation::getDroppedAxes() was added after PX4 v1.17.0.
file(STRINGS ${PX4_SOURCE_DIR}/src/lib/control_allocation/control_allocation/ControlAllocation.hpp
	_dropped_axes_api REGEX "getDroppedAxes")

if(_dropped_axes_api)
	target_compile_definitions(actuator_lint_engine PRIVATE ACTUATOR_LINT_ENGINE_HAS_DROPPED_AXES)
endif()

set(_engine_libs
	VehicleActuatorEffectiveness
	ControlAllocation
	px4_layer
	px4_platform
	uORB
	systemlib
	cdev
	px4_work_queue
	px4_daemon
	work_queue
	parameters
	events
	perf
	tinybson
	uorb_msgs
)

target_link_libraries(actuator_lint_engine PRIVATE ${_engine_libs})

# Fewer runtime dependencies for a binary that is copied to other machines.
if(NOT APPLE)
	target_link_options(actuator_lint_engine PRIVATE -static-libstdc++ -static-libgcc)
endif()
