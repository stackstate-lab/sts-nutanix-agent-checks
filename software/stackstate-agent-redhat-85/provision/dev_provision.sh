#!/bin/bash

echo "n" | sh -c "$(curl -fsSL https://raw.github.com/ohmyzsh/ohmyzsh/master/tools/install.sh)"

# Copy in the default .zshrc config file
cp ~/.oh-my-zsh/templates/zshrc.zsh-template ~/.zshrc

# Change the oh my zsh default theme.
sed -i 's/ZSH_THEME="robbyrussell"/ZSH_THEME="agnoster"/g' ~/.zshrc
sed -i 's/plugins=.*/plugins=(git kubectl)/g' ~/.zshrc

# Default shell for vagrant user
sudo chsh -s /bin/zsh vagrant
