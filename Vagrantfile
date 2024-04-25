# -*- mode: ruby -*-
# vi: set ft=ruby :

Vagrant.configure("2") do |config|
  # Define the base box
  config.vm.box = "centos/8"

  # Ansible Tower Server
  config.vm.define "ansible_tower" do |ansible_tower|
    ansible_tower.vm.hostname = "ansible-tower"
    ansible_tower.vm.network "private_network", ip: "192.168.56.10"
    ansible_tower.vm.network "public_network"

    # Adding a shell script provisioner to run updateOS.sh as root
    ansible_tower.vm.provision "shell", path: "updateCentos.sh", privileged: true
  end

  # Deployment Environment 1
  config.vm.define "deploy_env1" do |deploy_env1|
    deploy_env1.vm.hostname = "deploy-env1"
    deploy_env1.vm.network "private_network", ip: "192.168.56.11"
    deploy_env1.vm.network "public_network"

    # Adding a shell script provisioner to run updateOS.sh as root
    deploy_env1.vm.provision "shell", path: "updateCentos.sh", privileged: true
  end

  # Deployment Environment 2
  config.vm.define "deploy_env2" do |deploy_env2|
    deploy_env2.vm.hostname = "deploy-env2"
    deploy_env2.vm.network "private_network", ip: "192.168.56.12"
    deploy_env2.vm.network "public_network"

    # Adding a shell script provisioner to run updateOS.sh as root
    deploy_env2.vm.provision "shell", path: "updateCentos.sh", privileged: true
  end

  # Provisioning with Ansible (Optional)
  # config.vm.provision "ansible" do |ansible|
  #   ansible.playbook = "playbook.yml"
  # end
end
