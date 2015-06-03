# -*- mode: ruby -*-
# vi: set ft=ruby :

VAGRANTFILE_API_VERSION = '2'

Vagrant.configure(VAGRANTFILE_API_VERSION) do |config|
  ## for KVM box
  ##config.vm.box = 'ubuntu/trusty64'
  ## for LXC vagrant
  config.vm.box = 'fgrehm/trusty64-lxc'
  config.vm.hostname = "vagrant-lxc-ironic-u7.apyz.internal-gmo"
  #
  config.vm.define 'ironic' do |ironic|
    #ironic.vm.provider :virtualbox do |vb|
    #  vb.customize ['modifyvm', :id,'--memory', '2048']
    #end

    #ironic.vm.network 'private_network', ip: '192.168.99.11' # It goes to 11.
    ironic.vm.provider :lxc do |lxc|
      lxc.customize 'cgroup.memory.limit_in_bytes', '2048M'
      ##
      lxc.container_name = "vagrant-lxc-ironic-u7.apyz.internal-gmo"
      lxc.customize 'network.type', 'veth'
      ## Error #lxc.customize 'network.name', 'eth0'
      #lxc.customize 'network.mtu',  '1500'
      lxc.customize 'network.link', 'virtbr0'
      #lxc.customize 'network.flags', 'up'
      lxc.customize 'network.ipv4', '192.168.99.11/24'
      lxc.customize 'network.ipv4.gateway', '192.168.99.1'
    end

    $script = <<SCRIPT
echo "nameserver 8.8.8.8" >> /etc/resolv.conf
SCRIPT
    ironic.vm.provision "shell", inline: $script

    ironic.vm.provision 'ansible' do |ansible|
      ansible.verbose = 'v'
      ansible.playbook = 'vagrant.yml'
      ansible.extra_vars = {
          ip: '192.168.99.11'
      }
    end
  end
end
