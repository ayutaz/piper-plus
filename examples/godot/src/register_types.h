#ifndef PIPER_REGISTER_TYPES_H
#define PIPER_REGISTER_TYPES_H

#include <gdextension_interface.h>
#include <godot_cpp/core/class_db.hpp>
#include <godot_cpp/core/defs.hpp>
#include <godot_cpp/godot.hpp>

void initialize_piper_tts(godot::ModuleInitializationLevel p_level);
void uninitialize_piper_tts(godot::ModuleInitializationLevel p_level);

#endif // PIPER_REGISTER_TYPES_H
