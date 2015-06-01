# -*- mode: ruby -*-
# vi: set ft=ruby :

VAGRANTFILE_API_VERSION = '2'

Vagrant.configure(VAGRANTFILE_API_VERSION) do |config|
  #
  ##config.vm.box = 'ubuntu/trusty64'
  config.vm.box = 'fgrehm/trusty64-lxc'
  config.vm.hostname = "vagrant-lxc-ironic-u7.apyz.internal-gmo"
  #
  config.vm.define 'ironic' do |ironic|
    #ironic.vm.provider :virtualbox do |vb|
    #  vb.customize ['modifyvm', :id,'--memory', '2048']
    #end

    #ironic.vm.network 'private_network', ip: '192.168.99.11' # It goes to 11.
    ironic.vm.provider :lxc do |lxc|
      lxc.container_name = "vagrant-lxc-ironic-u7.apyz.internal-gmo"
      lxc.customize 'network.type', 'veth'
      lxc.customize 'network.link', 'lxcbr0'
      lxc.customize 'network.ipv4', '192.168.99.11/32'
    end

    ironic.vm.provision 'ansible' do |ansible|
      ansible.verbose = 'v'
      ansible.playbook = 'vagrant.yml'
      ansible.extra_vars = {
          ip: '192.168.99.11'
      }
    end
  end
end
