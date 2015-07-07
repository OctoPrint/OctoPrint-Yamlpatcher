$(function() {
    function YamlPatcherViewModel(parameters) {
        var self = this;

        self.diffView = undefined;

        self.patch = ko.observable();
        self.diff = ko.observableArray([{"text": "Preview...", "css": "separator"}]);

        self.patchJson = ko.observable();
        self.toBeApplied = ko.observable();

        self.invalidInput = ko.observable(false);

        self.patch.subscribe(function(newValue) {
            self.toBeApplied(undefined);
            self.patchJson(undefined);
            self.invalidInput(false);

            if (!newValue) {
                return;
            }

            if (self._parseAsYamlpatch(newValue)) {
                return;
            }
            log.debug("Input is not a valid Yamlpatcher patch, trying to parse as YAML");

            if (self._parseAsYaml(newValue)) {
                return;
            }
            log.debug("Input is not valid YAML either");
            self.invalidInput(true);
        });

        self._parseAsYamlpatch = function(data) {
            try {
                var patch = JSON.parse(data);
                if (self._validateYamlPatch(patch)) {
                    self.patchJson(patch);
                    self.invalidInput(false);
                    return true;
                }
            } catch (e) {
            }

            return false;
        };

        self._parseAsYaml = function(data) {
            try {
                var lines = data.split("\n");
                lines = _.filter(lines, function(line) {
                    return line.trim() != "...";
                });

                var node = jsyaml.load(lines.join("\n"));

                if (!_.isPlainObject(node)) {
                    return false;
                }

                var keys = _.keys(node);
                var path = [];

                while (_.isPlainObject(node) && keys.length == 1) {
                    path.push(keys[0]);
                    node = node[keys[0]];
                    keys = _.keys(node);
                }

                if (path.length == 0 && !_.isPlainObject(node)) {
                    return false;
                }

                var nodes = [];
                if (path.length == 0) {
                    _.each(keys, function(key) {
                        nodes.push([[key], node[key]]);
                    });
                } else {
                    nodes.push([path, node]);
                }

                var patch = [];
                _.each(nodes, function(entry) {
                    var p = entry[0];
                    var n = entry[1];

                    if (_.isPlainObject(n)) {
                        patch.push(["merge", p.join("."), n]);
                    } else if (_.isArray(n)) {
                        patch.push(["append", p.join("."), n]);
                    } else {
                        patch.push(["set", p.join("."), n]);
                    }
                });

                log.info("Loaded json from YAML:", patch);
                if (self._validateYamlPatch(patch)) {
                    self.patchJson(patch);
                    self.invalidInput(false);
                    return true;
                }
            } catch (e2) {
            }

            return false;
        };

        self._validateYamlPatch = function(patch) {
            if (!_.isArray(patch)) {
                return false;
            }

            return _.every(patch, function(p) {
                if (!_.isArray(p) || p.length != 3) {
                    return false;
                }

                if (!_.isString(p[0])) {
                    return false;
                }

                if (!_.isString(p[1]) && !_.isArray(p[1])) {
                    return false;
                }

                if (p[0] == "merge" && !(_.isArray(p[2]) || _.isPlainObject(p[2]) || _.isString(p[2]))) {
                    return false;
                }

                return true;
            });
        };

        self.preview = function() {
            var patch = self.patchJson();
            if (!self.patchJson()) {
                return;
            }

            $.ajax({
                url: API_BASEURL + "plugin/yamlpatcher",
                type: "POST",
                dataType: "json",
                data: JSON.stringify({
                    command: "preview",
                    target: "settings",
                    patch: patch
                }),
                contentType: "application/json; charset=UTF-8",
                success: function(response) {
                    var contextSize = 3;
                    var diff = JsDiff.diffLines(response.old, response.new);

                    self.diff.removeAll();

                    if (diff.length <= 1) {
                        // no changes
                        self.diff.push({text: "No changes!", css: "separator"});
                        return;
                    }

                    self.toBeApplied(patch);

                    var unchanged = "";
                    var beginning = true;
                    var context, before, after, hidden;

                    _.each(diff, function(part) {
                        if (!part.added && !part.removed) {
                            unchanged += part.value;
                        } else {
                            if (unchanged) {
                                context = unchanged.split("\n");

                                if (context.length > contextSize * 2) {
                                    before = context.slice(0, contextSize);
                                    after = context.slice(-contextSize - 1);

                                    if (!beginning) {
                                        hidden = context.length - 2 * contextSize;
                                        self.diff.push({text: before.join("\n"), css: "unchanged"});
                                        self.diff.push({text: "\n[... " + hidden + " lines ...]\n", css: "separator"});
                                    } else {
                                        hidden = context.length - contextSize;
                                        self.diff.push({text: "[... " + hidden + " lines ...]\n", css: "separator"});
                                    }
                                    self.diff.push({text: after.join("\n"), css: "unchanged"});
                                } else {
                                    self.diff.push({text: context.join("\n"), css: "unchanged"})
                                }
                                unchanged = "";
                                beginning = false;
                            }

                            var css = part.added ? "added" : "removed";
                            self.diff.push({text: part.value, css: css});
                        }
                    });

                    if (unchanged) {
                        context = unchanged.split("\n");

                        if (context.length > contextSize) {
                            hidden = context.length - contextSize;
                            context = context.slice(0, contextSize);
                            self.diff.push({text: context.join("\n"), css: "unchanged"});
                            self.diff.push({text: "\n[... " + hidden + " lines ...]", css: "separator"});
                        } else {
                            self.diff.push({text: context.join("\n"), css: "unchanged"});
                        }
                    }
                }
            })
        };

        self.apply = function() {
            if (!self.toBeApplied()) {
                return;
            }

            $.ajax({
                url: API_BASEURL + "plugin/yamlpatcher",
                type: "POST",
                dataType: "json",
                data: JSON.stringify({
                    command: "apply",
                    target: "settings",
                    patch: self.toBeApplied()
                }),
                contentType: "application/json; charset=UTF-8",
                success: function(response) {
                    self.patch("");
                    self.diff.removeAll();
                    self.toBeApplied(undefined);
                }
            });
        };

        self.onStartup = function() {
            self.diffView = $("#settings_plugin_yamlpatcher_diffView");
        }
    }

    OCTOPRINT_VIEWMODELS.push([
        YamlPatcherViewModel,
        [],
        "#settings_plugin_yamlpatcher"
    ]);
});
