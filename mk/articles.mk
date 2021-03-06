# article paths always have the form $(ARTICLE_DIR)/<article name>/<revision>.yml

$(ARTICLE_DIR)/%.raw.json: $(ARTICLE_DIR)/%.md
	$(info parsing '$*'...)
	@$(MK)/bin/mwtoast --json < $< > $@

$(ARTICLE_DIR)/%.json: $(ARTICLE_DIR)/%.raw.json
	$(info normalizing $(word 2,$(call dirsplit,$@)))
	@$(MK)/bin/mfnf_ex -c $(BASE)/config/mfnf.yml \
		default normalize \
		--texvccheck-path $(MK)/bin/texvccheck \
		< $< > $@

$(ARTICLE_DIR)/%.md:
	@$(call create_directory,$(dir $@))
	$(eval UNESCAPED := $(call unescape,$(word 2,$(call dirsplit,$@))))
	$(info fetching source of $(UNESCAPED)...)
	@curl -sgsf -G 'https://de.wikibooks.org/w/index.php' \
		--data-urlencode action=raw \
		--data-urlencode title=$(UNESCAPED) \
		--data-urlencode oldid='$(notdir $*)' \
	> $@
