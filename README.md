> ⚠ **Note**
>
> This plugin targets developers, not endusers. It is not actively maintained since it does what is needed from it for regular OctoPrint development activities. If someone wants to make it more versatile and add more or fix existing functionality, feel free to get in touch about adoption on the [community forums](https://community.octoprint.org/c/plugins) about it.

# OctoPrint Yamlpatcher Plugin

The OctoPrint Yamlpatcher Plugin allows patching OctoPrint's [`config.yaml`](http://docs.octoprint.org/en/master/configuration/config_yaml.html)
through a new dialog within OctoPrint's settings, using easily shareable
patch strings.

This allows applying configuration changes that are not easily achievable through
the UI even for users who don't feel comfortable manually editing a YAML
configuration file. And for those that do feel comfortable with YAML, it is
also is a very fast way to make quick adjustments to configuration settings for
which no UI inputs exist, e.g. [development settings](http://docs.octoprint.org/en/master/configuration/config_yaml.html#development-settings).

Before allowing to apply the patch string, the plugin will present the user
with a preview of the changes that will take place, visualizing both added
and removed entries within `config.yaml`.

![](http://i.imgur.com/Xs1xGHu.png)

![JSON patch string](http://i.imgur.com/0Av9NB5.gif)

![YAML patch string](http://i.imgur.com/VzHeRHn.gif)

## Setup

Install via the bundled [Plugin Manager](https://github.com/foosel/OctoPrint/wiki/Plugin:-Plugin-Manager)
or manually using this URL:

    https://github.com/OctoPrint/OctoPrint-Yamlpatcher/archive/master.zip

## Usage

Paste a valid patch string into the input field below, then hit the "Preview" button. Make sure the changes look like they should (if a screenshot of a preview was provided along side the patch string, compare!). If they do, hit "Apply". Then restart your server.

## Patch format

The plugin supports two kinds of patch strings, a special JSON based format
that allows very specific manipulation of the configuration, and
YAML dictionaries that will just get merged with the existing configuration.

### JSON patch string

The JSON patch string format consists of a JSON string specifying a list of
changes to apply to the configuration, in the order they occur in the list.

Each change consists of a list with three elements:

  * an **action** to take,
  * a **path** specifying the node within the configuration on which to
    perform the action and
  * additional **parameters** for the action.

Since it is possible to minimize JSON quite well, even more complex patch sets
become very compact:

``` json
[["merge","plugins.softwareupdate",{"checks":{"octoprint":{"checkout_folder":"/home/pi/OctoPrint"}},"octoprint_restart_command":"sudo service octoprint restart","environment_restart_command":"sudo shutdown -r now"}]]
```

Currently the plugin understands changes that specify one of the following
actions: ``set``, ``merge``, ``remove``, ``append``, ``move``.

#### set

Sets a new value at the specified path, completely replacing the existing value.
If the path does not yet exist, it will be created. Use this to set a specific
value at a specific path in the structure, ignoring what might already be there.

Example patch sets:

  * **Set ``server.firstRun`` and ``accessControl.enabled`` to ``true``**

    ``` json
    [
      ["set", "server.firstRun", true],
      ["set", "accessControl.enabled", true]
    ]
    ```
  * **Set ``plugins.softwareupdate.checks.octoprint.checkout_folder`` to ``/home/pi/OctoPrint``**

    ``` json
    [
      ["set", "plugins.softwareupdate.checks.octoprint.checkout_folder", "/home/pi/OctoPrint"]
    ]
    ```

#### merge

Updates the value at the specified path, merging it with the new provided data.
If the path does not yet exist, it will be created (and only contain the value
to be merged).

If the target node and the value are dictionaries, both will be merged (the new
data overwriting the old one in case of conflicts).

If the target node is a list and the value a list, the existing list will be
extended by all entries in the value.

Example patch sets:

* **Merge the OctoPrint update configuration for OctoPi unto the config**

  ``` json
  [
    [
      "merge",
      "plugins.softwareupdate",
      {
        "checks": {
          "octoprint": {
            "checkout_folder": "/home/pi/OctoPrint"
          }
        },
        "octoprint_restart_command": "sudo service octoprint restart",
        "environment_restart_command": "sudo shutdown -r now"
      }
    ]
  ]
  ```

#### remove

Removes the node at the specified path if its parent is a dictionary. If not
and it is a list, removes the provided value from the list.

Example patch sets:

  * **Remove the ``plugins.softwareupdate.checks.remove_me`` node**

    ``` json
    [
      ["remove", "plugins.softwareupdate.checks.remove_me", ""]
    ]
    ```

  * **Remove the ``/dev/printer`` entry from ``serial.additionalPorts``**

    ``` json
    [
      ["remove", "serial.additionalPorts", "/dev/printer"]
    ]
    ```

#### append

Appends a value to a list node specified by the given path. If the list node
doesn't already exist it will be created.

Example patch sets:

  * **Append a ``/dev/printer`` entry to ``serial.additionalPorts``**:

    ``` json
    [
      ["append", "serial.additionalPorts", "/dev/printer"]
    ]
    ```

#### move

Moves the value from one node in the config to another, optionally creating the
target path if necessary.

Example patch sets:

  * **Move the value from ``plugins.someplugin.somekey`` to ``plugins.someotherplugin.someotherkey``**

    ``` json
    [
      ["move", "plugins.someplugin.somekey", "plugins.someotherplugin.someotherkey"]
    ]
    ```
  * **Backup the current API key, then set a new one**

    ``` json
    [
      ["move", "api.key", "api.backupkey"],
      ["set", "api.key", "IamNotVerySecureNowAmI"]
    ]
    ```

### YAML dictionary

The plugin also accepts YAML dictionaries as input. It will parse them client-side
and convert them into JSON ``merge`` patch sets.

In order to allow copy-pasting of existing configuration examples for OctoPrint
in wiki, mailinglist etc, if the plugin detects a possible YAML input it will
strip any lines that only consist of ``...`` before attempting to parse the input.

Hence, for the plugin this would be a valid input, although it is not valid
YAML due to the contained ``...``:

``` yaml
accessControl:
  enabled: true
...
server:
  firstRun: true
```

This allows for most of the existing examples to just be directly copy-pasted
into the input field and merged on the existing configuration.

## Acknowledgements & Licensing

The OctoPrint Yamlpatcher Plugin is licensed under the terms of the [AGPLv3](http://opensource.org/licenses/AGPL-3.0)
(also included).

It uses [jsdiff](https://github.com/kpdecker/jsdiff) by Kevin Decker which is
licensed under the terms of the [BSD license](http://opensource.org/licenses/BSD-3-Clause),
and [js-yaml](https://github.com/nodeca/js-yaml) by Vitaly Puzrin which is
licensed under the terms of the [MIT license](http://opensource.org/licenses/MIT)
