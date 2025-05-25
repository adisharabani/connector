# Home Automation Connector

A powerful home automation bridge that enables seamless integration between different smart home protocols and devices. This connector allows you to create bindings between devices from different ecosystems, enabling them to work together harmoniously.

## Supported Protocols

The connector currently supports the following protocols:

1. **MQTT**
   - Enables communication with MQTT-enabled devices
   - Supports custom protocols for different device types (e.g., Nuki locks, coverings)
   - Allows bidirectional communication with devices

2. **Lutron**
   - Integrates with Lutron lighting and fan control systems
   - Supports both device control and system variable monitoring
   - Enables LED control for keypads

3. **Bond**
   - Connects to Bond Bridge for controlling ceiling fans
   - Supports fan speed and power control

4. **Nuki**
   - Integrates with Nuki smart locks
   - Supports lock/unlock actions and auto-lock functionality
   - Can be controlled via MQTT or direct API

## Configuration

The connector is configured using a YAML file (`config.yaml`). The configuration consists of two main sections: `services` and `bindings`.

### Services Configuration

Each supported protocol needs to be configured under the `services` section:

```yaml
services:
  mqtt:
    host: <mqtt_broker_ip>
    username: <mqtt_username>
    password: <mqtt_password>
    topic: <mqtt_topic>
    protocols:
      # Protocol-specific configurations
      nuki:
        state_suffix: /state
        states: [1, 3]  # Lock states
        command_suffix: /lockAction
        commands: [2, 1]  # Lock commands
      covering:
        state_suffix: /state
        states: [closed, open]
        command_suffix: /lockAction
        commands: [close, open]

  lutron:
    host: <lutron_host>
    port: <lutron_port>
    username: <lutron_username>
    password: <lutron_password>

  bond:
    address: <bond_bridge_ip>
    port: <bond_port>
    token: <bond_token>

  nuki:
    api_key: <nuki_api_key>
```

### Bindings Configuration

Bindings define the relationships between different devices. Each binding can be:
- One-way (direction: one-way)
- Two-way (default, no direction specified)

#### Binding Syntax Variations

The connector supports multiple syntax variations for defining bindings. Here are the different ways to specify device bindings:

1. **Short Form (Direct Device ID)**
```yaml
- binding:
    - lutron: <integration_id>  # Direct device ID
    - bond: <bond_device_id>
```
This is equivalent to the expanded form:
```yaml
- binding:
    - lutron:
        - device: <integration_id>
    - bond:
        - device: <bond_device_id>
```

2. **Method Calls with Parameters**
```yaml
- binding:
    - nuki:
        - device: <Nuki_web_api_device_id>
        - autolock  # Method without parameters
        - inverse   # Method without parameters
    - lutron:
        - keypad:      # Method with parameters
            id: <integration_id>
            button: 1
            action: 2
```

3. **Nested Device Configuration**
```yaml
- binding:
    - mqtt:
        - device:
            topic: nuki/<Nuki_local_device_id>
            protocol: nuki
    - lutron:
        - sysvar: <sysvar_id>
```

#### Method Call Types

1. **Simple Methods (No Parameters)**
```yaml
- binding:
    - nuki:
        - device: <device_id>
        - autolock    # Simple method
        - inverse     # Simple method
```

2. **Methods with Parameters**
```yaml
- binding:
    - lutron:
        - keypad:        # Method with parameter object
            id: <integration_id>
            button: 82  # Led of second button
            action: 2   # slow blink
```

3. **Protocol-Specific Methods**
Each protocol may support different methods:

**MQTT Protocol Methods:**
```yaml
- binding:
    - mqtt:
        - device:
            topic: <topic>
            protocol: nuki    # Protocol-specific configuration
            # Protocol methods are defined in services.mqtt.protocols
```

**Lutron Methods:**
```yaml
- binding:
    - lutron:
        - device: <device_id>     # Direct device control
        - sysvar: <sysvar_id>     # System variable
        - keypad:                 # Keypad control
            id: <keypad_id>
            button: <button_id>   # use 81,82... to control the leds (actions 0 off, 1 on, 2 slow blink, 3 rapid blink)
            action: <action_id>   # 1=press, 2=release, 3=long press, 4=double press
```

**Nuki Methods:**
```yaml
- binding:
    - nuki:
        - device: <device_id>
        - autolock               # Enable auto-lock
        - inverse               # Invert the lock state
```

#### Binding Examples with Different Syntaxes

1. **Simple Device Binding (Short Form)**
```yaml
- binding:
    - lutron: <lutron_device_id>
    - bond: <bond_device_id>
```

2. **Device Binding with Methods (Expanded Form)**
```yaml
- binding:
    - nuki:
        - device: <nuki_web_device_id>
        - autolock
        - inverse
    - mqtt:
        - device:
            topic: nuki/385D087C
            protocol: nuki
    direction: one-way
    filter: [1] # only act on turning on
```

3. **System Variable to Device Binding**
```yaml
- binding:
    - lutron:
        - sysvar: <sysvar_integration_id>
    - mqtt:
        - device:
            topic: nuki/385D087C
            protocol: nuki
    direction: one-way
```

4. **Keypad Control Binding with Parameters**
```yaml
- binding:
    - lutron:
        - sysvar: <sysvar_integration_id>
    - lutron:
        - keypad:
            id: <keypad_integration_id>
            button: 81 # This will control the led of the first button
            action: 2  # Slow Blink
    direction: one-way
```

5. **LED Feedback**
   - Control Lutron keypads based on system events
   - Provide visual feedback for various states using keypad actions

## Use Cases

1. **Smart Lock Integration**
   - Control Nuki locks via Lutron keypads
   - Monitor lock states through MQTT
   - Implement auto-lock functionality

2. **Fan Control**
   - Control ceiling fans using Lutron switches
   - Synchronize fan states between Lutron and Bond controllers

3. **Cover Control**
   - Monitor pool cover state via MQTT
   - Control Lutron devices based on cover state

4. **LED Feedback**
   - Control Lutron keypad LEDs based on system events
   - Provide visual feedback for various states

## Security Considerations

1. Store sensitive credentials (passwords, API keys) securely
2. Use appropriate access controls for MQTT topics
3. Implement proper network segmentation
4. Regularly rotate credentials and tokens

## Installation

[Installation instructions to be added based on deployment method]

## Contributing

[Contribution guidelines to be added]

## License

[License information to be added] 