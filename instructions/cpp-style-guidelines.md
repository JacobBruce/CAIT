# C++ Style Guidelines

This document provides a set of standards, conventions, and guidelines that should be followed when writing C++ code.

## Philosophy

- Prefer **modern C++** over C-style patterns.
- Target **C++20** unless a project specifies otherwise.
- Prefer **clarity and safety** over brevity.
- Keep names, types, and scope **explicit** — avoid shortcuts that hide intent.
- Match existing project conventions when they differ; otherwise follow this guide.

## Naming Conventions

### Summary

| Category | Convention | Examples |
|----------|------------|----------|
| Namespaces | PascalCase | `Utils`, `WordParser` |
| Types (class, struct, enum, typedef, using) | PascalCase | `Scene`, `LogLevel` |
| Functions / methods | PascalCase | `GetName`, `IsPaused` |
| Files | PascalCase (match primary type) | `Scene.h`, `Scene.cpp` |
| Local variables | snake_case | `retry_count`, `file_path` |
| Function parameters | snake_case | `scene_name`, `buffer_size` |
| Struct fields | snake_case, no prefix | `host_name`, `port_number` |
| Public class members | lowerCamelCase | `displayName`, `isVisible` |
| Private / protected class members | `m_` + lowerCamelCase | `m_name`, `m_isPaused` |
| Static mutable class members | `s_` + lowerCamelCase | `s_instanceCount` |
| Named constants (`constexpr`) | `c_` + lowerCamelCase | `c_maxRetries`, `c_defaultTimeout` |
| Namespace-level variables | lowerCamelCase | `gpuDriver`, `fontLoader` |
| Enum class enumerators | PascalCase | `LogLevel::Warning`, `UpdateState::Idle` |
| Macros / special globals | SCREAMING_SNAKE_CASE | `MAX_PATH`, platform `#define`s |

Short names (`i`, `it`, `ctx`) are acceptable in tiny scopes when intent is obvious.

---

### Functions and Methods

| Kind | Pattern | Examples |
|------|---------|----------|
| Action | Verb | `Resume`, `Pause`, `Load`, `Clear` |
| Predicate | `Is` / `Has` / `Can` | `IsPaused`, `HasChildren`, `CanRetry` |
| Getter | `Get` + noun | `GetName`, `GetSize` |
| Setter | `Set` + noun | `SetName`, `SetLabel` |

Always use the full `Get`/`Set` prefix — do not use bare `Name()` for getters.

---

### Variables

**Locals and parameters** both use `snake_case`. No prefix is required; scope distinguishes them.

```cpp
void ProcessScene(Scene& scene, const std::string& file_path)
{
	const auto& scene_name = scene.GetName();
	uint32_t retry_count = 0;

	if (file_path.empty())
		return;
}
```

When a parameter initializes a member, naming stays natural:

```cpp
Scene::Scene(std::string scene_name)
	: m_name(std::move(scene_name))
{
}
```

---

### Class Members

Use different conventions by visibility and role so members are recognizable at a glance:

| Kind | Convention | Example |
|------|------------|---------|
| Public | lowerCamelCase | `displayName` |
| Private / protected | `m_` + lowerCamelCase | `m_name`, `m_isPaused` |
| Static mutable | `s_` + lowerCamelCase | `s_instanceCount` |
| Static `constexpr` | `c_` + lowerCamelCase | `c_maxInstances` |

**Policy for public data members:**

- Prefer **getters/setters** and keep state private.
- Avoid public data members on classes when possible.
- If a public field is truly needed, prefer multi-word `lowerCamelCase` names (`displayName`, not `name`) to avoid confusion with local `snake_case` variables.
- Use **structs** for plain data with no prefix and `snake_case` fields.

Place **private and protected members at the bottom** of the class, after the public interface.

---

### Namespace-Level Variables

Treat namespace-level variables that form part of a module's public API the same as **public class members** — use **lowerCamelCase**.

This distinguishes module-level state from local `snake_case` variables and from `snake_case` struct fields.

```cpp
namespace Ultralight {

	using namespace ultralight;

	inline RefPtr<Renderer> renderer;
	inline GPUDriverGL* gpuDriver = nullptr;
	inline UIFontLoader fontLoader;

} // namespace Ultralight
```

`using namespace` is **not** acceptable at global scope or to shortcut standard library names. It is acceptable **only** inside a wrapper namespace that intentionally bridges a third-party library into your project's naming convention, as shown above.

**Never** use `using namespace std;`.

---

### Structs

Use structs for plain data with no behavior. Fields use `snake_case` with no prefix:

```cpp
struct RenderConfig {
	std::string shader_path;
	uint32_t msaa_samples = 4;
};
```

---

### Constants

Use the `c_` prefix for **named compile-time constants** — values that are fixed and reused, not ordinary variables.

| Scope | Convention | Example |
|-------|------------|---------|
| Namespace / file scope | `c_` + lowerCamelCase | `c_maxRetryCount`, `c_defaultPort` |
| Class `static constexpr` | `c_` + lowerCamelCase | `c_maxConnections` |
| Function-local `const` | `snake_case` (no prefix) | `const auto& file_path` |

```cpp
namespace Network {

	inline constexpr uint32_t c_defaultPort = 8080;
	inline constexpr float c_connectTimeout = 5.0f;

} // namespace Network

class ConnectionPool {
public:
	static constexpr size_t c_maxConnections = 256;

private:
	static uint32_t s_activeCount;
};
```

- Do **not** use `c_` for function-local `const` variables — scope already limits their role.
- Use `s_` only for **mutable** static members (`s_activeCount`), not for constants.
- Reserve **SCREAMING_SNAKE_CASE** for macros, platform `#define`s, and unavoidable C-style global constants.

### Enums

```cpp
enum class UpdateState {
	Idle,
	Running,
	Paused,
	Failed
};
```

- `enum class` enumerators: **PascalCase** (scoped by the enum type name)
- Prefer `enum class` over unscoped `enum`

## Formatting

### General

- **Indentation:** use tabs for clear line indentation
- **Braces:** Allman style — opening `{` on its own line (except for loops and function blocks)
- **`const` placement:** east const — `const std::string&`, not `std::string const&`

### Pointers and References

Bind `*` and `&` to the **type**, not the variable name:

```cpp
bool MyFunction(std::vector<std::string>& vec);
const std::string* FindKey(const Map& map);
```

### Control Flow

**`if` without `else`:**

- Short body — one line is fine:

```cpp
if (Utils::CheckSomething()) return false;
```

- Longer body — two lines, no braces:

```cpp
if (Utils::CheckSomethingComplex(arg1, arg2))
	Utils::HandleFailure(arg1, arg2);
```

**`if/else`:** always use braces:

```cpp
if (str == "abc") {
	Utils::DoSomething(str);
} else {
	Utils::SomethingElse(str);
}
```

## Types

### Fixed-Width Integers

Prefer **explicit fixed-width types** from `<cstdint>` over plain `unsigned int`, `long`, etc.:

```cpp
uint32_t buffer_size = 0;
int64_t timestamp = 0;
```

Use `size_t` for sizes and indices into containers. Use fixed-width types for wire formats, file headers, binary protocols, and anywhere bit width matters.

### Modern C++ (C++20)

- Use `nullptr`, not `NULL` or `0`
- Prefer `enum class` over unscoped `enum`
- Mark single-argument constructors `explicit` unless implicit conversion is intentional
- Use `override` (and `final` when appropriate) on virtual overrides
- Use `auto` **only when the type name is long or unwieldy**; prefer explicit types when the type is short and clarity matters
- Prefer range-based `for` loops over manual index loops when iterating containers
- Prefer smart pointers (`std::unique_ptr`, `std::shared_ptr`) over raw `new`/`delete`
- Prefer `static_cast`, `reinterpret_cast`, etc. over C-style casts
- Use RAII for resource management
- Use `[[nodiscard]]` on functions whose return values must not be ignored
- Initialize members in **constructor initializer lists**; use **default member initializers** in the class body when appropriate
- Avoid macros for constants and inline logic; use `constexpr`, `inline`, and templates instead

## Documentation

Follow **Doxygen** conventions:

| Use | Syntax |
|-----|--------|
| Single-line | `///` above the declaration |
| Multi-line | `/** ... */` block |

Use `@param`, `@return`, and `@brief` when they add clarity.

## Files and Headers

- One primary type per header pair when practical
- File names match the primary type: `Scene.h`, `Scene.cpp`
- Use **`#pragma once`** for include guards
- Include what you use; prefer forward declarations in headers to reduce compile dependencies
- Keep implementation in the **`.h` file if under 100 lines**; otherwise split into `.h` / `.cpp`

## Class Example

```cpp
#pragma once
#include <cstdint>
#include <string>
#include <vector>

/**
 * Manages scene lifecycle and update state.
 * Each scene is identified by a unique name string.
 */
class Scene {
public:

	Scene(std::string scene_name);
	~Scene();

	/// Returns the unique scene identifier name.
	const std::string& GetName() const;

	/// Returns the number of active scenes across all instances.
	static uint32_t GetActiveCount();

	static constexpr uint32_t c_maxNameLength = 256;

	// Public data member — avoid when possible; prefer getters/setters.
	uint32_t updatePriority = 0;

protected:

	bool m_isLoaded = false;

private:

	std::string m_name;

	static uint32_t s_activeCount;
};
```