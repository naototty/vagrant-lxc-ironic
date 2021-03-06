# -*- encoding: utf-8 -*-
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.
"""
Tests for the API /nodes/ methods.
"""

import datetime
import json

import mock
from oslo_config import cfg
from oslo_utils import timeutils
from oslo_utils import uuidutils
import six
from six.moves.urllib import parse as urlparse
from testtools.matchers import HasLength
from wsme import types as wtypes

from ironic.api.controllers import base as api_base
from ironic.api.controllers import v1 as api_v1
from ironic.api.controllers.v1 import node as api_node
from ironic.api.controllers.v1 import utils as api_utils
from ironic.common import boot_devices
from ironic.common import exception
from ironic.common import states
from ironic.conductor import rpcapi
from ironic import objects
from ironic.tests.api import base as test_api_base
from ironic.tests.api import utils as test_api_utils
from ironic.tests import base
from ironic.tests.objects import utils as obj_utils


class TestNodeObject(base.TestCase):

    def test_node_init(self):
        node_dict = test_api_utils.node_post_data()
        del node_dict['instance_uuid']
        node = api_node.Node(**node_dict)
        self.assertEqual(wtypes.Unset, node.instance_uuid)


class TestListNodes(test_api_base.FunctionalTest):

    def setUp(self):
        super(TestListNodes, self).setUp()
        self.chassis = obj_utils.create_test_chassis(self.context)
        p = mock.patch.object(rpcapi.ConductorAPI, 'get_topic_for')
        self.mock_gtf = p.start()
        self.mock_gtf.return_value = 'test-topic'
        self.addCleanup(p.stop)

    def _create_association_test_nodes(self):
        # create some unassociated nodes
        unassociated_nodes = []
        for id in range(3):
            node = obj_utils.create_test_node(self.context,
                                              uuid=uuidutils.generate_uuid())
            unassociated_nodes.append(node.uuid)

        # created some associated nodes
        associated_nodes = []
        for id in range(4):
            node = obj_utils.create_test_node(
                    self.context, uuid=uuidutils.generate_uuid(),
                    instance_uuid=uuidutils.generate_uuid())
            associated_nodes.append(node.uuid)
        return {'associated': associated_nodes,
                'unassociated': unassociated_nodes}

    def test_empty(self):
        data = self.get_json('/nodes')
        self.assertEqual([], data['nodes'])

    def test_one(self):
        node = obj_utils.create_test_node(self.context,
                                          chassis_id=self.chassis.id)
        data = self.get_json('/nodes',
                 headers={api_base.Version.string: str(api_v1.MAX_VER)})
        self.assertIn('instance_uuid', data['nodes'][0])
        self.assertIn('maintenance', data['nodes'][0])
        self.assertIn('power_state', data['nodes'][0])
        self.assertIn('provision_state', data['nodes'][0])
        self.assertIn('uuid', data['nodes'][0])
        self.assertEqual(node.uuid, data['nodes'][0]["uuid"])
        self.assertNotIn('driver', data['nodes'][0])
        self.assertNotIn('driver_info', data['nodes'][0])
        self.assertNotIn('driver_internal_info', data['nodes'][0])
        self.assertNotIn('extra', data['nodes'][0])
        self.assertNotIn('properties', data['nodes'][0])
        self.assertNotIn('chassis_uuid', data['nodes'][0])
        self.assertNotIn('reservation', data['nodes'][0])
        self.assertNotIn('console_enabled', data['nodes'][0])
        self.assertNotIn('target_power_state', data['nodes'][0])
        self.assertNotIn('target_provision_state', data['nodes'][0])
        self.assertNotIn('provision_updated_at', data['nodes'][0])
        self.assertNotIn('maintenance_reason', data['nodes'][0])
        # never expose the chassis_id
        self.assertNotIn('chassis_id', data['nodes'][0])

    def test_get_one(self):
        node = obj_utils.create_test_node(self.context,
                                          chassis_id=self.chassis.id)
        data = self.get_json('/nodes/%s' % node.uuid,
                 headers={api_base.Version.string: str(api_v1.MAX_VER)})
        self.assertEqual(node.uuid, data['uuid'])
        self.assertIn('driver', data)
        self.assertIn('driver_info', data)
        self.assertEqual('******', data['driver_info']['fake_password'])
        self.assertEqual('bar', data['driver_info']['foo'])
        self.assertIn('driver_internal_info', data)
        self.assertIn('extra', data)
        self.assertIn('properties', data)
        self.assertIn('chassis_uuid', data)
        self.assertIn('reservation', data)
        self.assertIn('maintenance_reason', data)
        self.assertIn('name', data)
        self.assertIn('inspection_finished_at', data)
        self.assertIn('inspection_started_at', data)
        # never expose the chassis_id
        self.assertNotIn('chassis_id', data)

    def test_detail(self):
        node = obj_utils.create_test_node(self.context,
                                          chassis_id=self.chassis.id)
        data = self.get_json('/nodes/detail',
                 headers={api_base.Version.string: str(api_v1.MAX_VER)})
        self.assertEqual(node.uuid, data['nodes'][0]["uuid"])
        self.assertIn('name', data['nodes'][0])
        self.assertIn('driver', data['nodes'][0])
        self.assertIn('driver_info', data['nodes'][0])
        self.assertIn('extra', data['nodes'][0])
        self.assertIn('properties', data['nodes'][0])
        self.assertIn('chassis_uuid', data['nodes'][0])
        self.assertIn('reservation', data['nodes'][0])
        self.assertIn('maintenance', data['nodes'][0])
        self.assertIn('console_enabled', data['nodes'][0])
        self.assertIn('target_power_state', data['nodes'][0])
        self.assertIn('target_provision_state', data['nodes'][0])
        self.assertIn('provision_updated_at', data['nodes'][0])
        self.assertIn('inspection_finished_at', data['nodes'][0])
        self.assertIn('inspection_started_at', data['nodes'][0])
        # never expose the chassis_id
        self.assertNotIn('chassis_id', data['nodes'][0])

    def test_detail_against_single(self):
        node = obj_utils.create_test_node(self.context)
        response = self.get_json('/nodes/%s/detail' % node.uuid,
                                 expect_errors=True)
        self.assertEqual(404, response.status_int)

    def test_mask_available_state(self):
        node = obj_utils.create_test_node(self.context,
                                          provision_state=states.AVAILABLE)

        data = self.get_json('/nodes/%s' % node.uuid,
                headers={api_base.Version.string: str(api_v1.MIN_VER)})
        self.assertEqual(states.NOSTATE, data['provision_state'])

        data = self.get_json('/nodes/%s' % node.uuid,
                headers={api_base.Version.string: "1.2"})
        self.assertEqual(states.AVAILABLE, data['provision_state'])

    def test_hide_fields_in_newer_versions_driver_internal(self):
        node = obj_utils.create_test_node(self.context,
                                          driver_internal_info={"foo": "bar"})
        data = self.get_json('/nodes/%s' % node.uuid,
                headers={api_base.Version.string: str(api_v1.MIN_VER)})
        self.assertNotIn('driver_internal_info', data)

        data = self.get_json('/nodes/%s' % node.uuid,
                headers={api_base.Version.string: "1.3"})
        self.assertEqual({"foo": "bar"}, data['driver_internal_info'])

    def test_hide_fields_in_newer_versions_name(self):
        node = obj_utils.create_test_node(self.context,
                                          name="fish")
        data = self.get_json('/nodes/%s' % node.uuid,
                headers={api_base.Version.string: "1.4"})
        self.assertNotIn('name', data)

        data = self.get_json('/nodes/%s' % node.uuid,
                headers={api_base.Version.string: "1.5"})
        self.assertEqual('fish', data['name'])

    def test_hide_fields_in_newer_versions_inspection(self):
        some_time = datetime.datetime(2015, 3, 18, 19, 20)
        node = obj_utils.create_test_node(self.context,
                                          inspection_started_at=some_time)
        data = self.get_json('/nodes/%s' % node.uuid,
                headers={api_base.Version.string: str(api_v1.MIN_VER)})
        self.assertNotIn('inspection_finished_at', data)
        self.assertNotIn('inspection_started_at', data)

        data = self.get_json('/nodes/%s' % node.uuid,
                headers={api_base.Version.string: "1.6"})
        started = timeutils.parse_isotime(
                data['inspection_started_at']).replace(tzinfo=None)
        self.assertEqual(some_time, started)
        self.assertEqual(None, data['inspection_finished_at'])

    def test_many(self):
        nodes = []
        for id in range(5):
            node = obj_utils.create_test_node(self.context,
                                              uuid=uuidutils.generate_uuid())
            nodes.append(node.uuid)
        data = self.get_json('/nodes')
        self.assertEqual(len(nodes), len(data['nodes']))

        uuids = [n['uuid'] for n in data['nodes']]
        self.assertEqual(sorted(nodes), sorted(uuids))

    def test_many_have_names(self):
        nodes = []
        node_names = []
        for id in range(5):
            name = 'node-%s' % id
            node = obj_utils.create_test_node(self.context,
                                              uuid=uuidutils.generate_uuid(),
                                              name=name)
            nodes.append(node.uuid)
            node_names.append(name)
        data = self.get_json('/nodes',
                headers={api_base.Version.string: "1.5"})
        names = [n['name'] for n in data['nodes']]
        self.assertEqual(len(nodes), len(data['nodes']))
        self.assertEqual(sorted(node_names), sorted(names))

    def test_links(self):
        uuid = uuidutils.generate_uuid()
        obj_utils.create_test_node(self.context, uuid=uuid)
        data = self.get_json('/nodes/%s' % uuid)
        self.assertIn('links', data.keys())
        self.assertEqual(2, len(data['links']))
        self.assertIn(uuid, data['links'][0]['href'])
        for l in data['links']:
            bookmark = l['rel'] == 'bookmark'
            self.assertTrue(self.validate_link(l['href'], bookmark=bookmark))

    def test_collection_links(self):
        nodes = []
        for id in range(5):
            node = obj_utils.create_test_node(self.context,
                                              uuid=uuidutils.generate_uuid())
            nodes.append(node.uuid)
        data = self.get_json('/nodes/?limit=3')
        self.assertEqual(3, len(data['nodes']))

        next_marker = data['nodes'][-1]['uuid']
        self.assertIn(next_marker, data['next'])

    def test_collection_links_default_limit(self):
        cfg.CONF.set_override('max_limit', 3, 'api')
        nodes = []
        for id in range(5):
            node = obj_utils.create_test_node(self.context,
                                              uuid=uuidutils.generate_uuid())
            nodes.append(node.uuid)
        data = self.get_json('/nodes')
        self.assertEqual(3, len(data['nodes']))

        next_marker = data['nodes'][-1]['uuid']
        self.assertIn(next_marker, data['next'])

    def test_sort_key(self):
        nodes = []
        for id in range(3):
            node = obj_utils.create_test_node(self.context,
                                              uuid=uuidutils.generate_uuid())
            nodes.append(node.uuid)
        data = self.get_json('/nodes?sort_key=uuid')
        uuids = [n['uuid'] for n in data['nodes']]
        self.assertEqual(sorted(nodes), uuids)

    def test_sort_key_invalid(self):
        invalid_key = 'foo'
        response = self.get_json('/nodes?sort_key=%s' % invalid_key,
                                 expect_errors=True)
        self.assertEqual(400, response.status_int)
        self.assertEqual('application/json', response.content_type)
        self.assertIn(invalid_key, response.json['error_message'])

    def test_ports_subresource_link(self):
        node = obj_utils.create_test_node(self.context)
        data = self.get_json('/nodes/%s' % node.uuid)
        self.assertIn('ports', data.keys())

    def test_ports_subresource(self):
        node = obj_utils.create_test_node(self.context)

        for id_ in range(2):
            obj_utils.create_test_port(self.context, node_id=node.id,
                                       uuid=uuidutils.generate_uuid(),
                                       address='52:54:00:cf:2d:3%s' % id_)

        data = self.get_json('/nodes/%s/ports' % node.uuid)
        self.assertEqual(2, len(data['ports']))
        self.assertNotIn('next', data.keys())

        # Test collection pagination
        data = self.get_json('/nodes/%s/ports?limit=1' % node.uuid)
        self.assertEqual(1, len(data['ports']))
        self.assertIn('next', data.keys())

    def test_ports_subresource_noid(self):
        node = obj_utils.create_test_node(self.context)
        obj_utils.create_test_port(self.context, node_id=node.id)
        # No node id specified
        response = self.get_json('/nodes/ports', expect_errors=True)
        self.assertEqual(400, response.status_int)

    def test_ports_subresource_node_not_found(self):
        non_existent_uuid = 'eeeeeeee-cccc-aaaa-bbbb-cccccccccccc'
        response = self.get_json('/nodes/%s/ports' % non_existent_uuid,
                                 expect_errors=True)
        self.assertEqual(404, response.status_int)

    @mock.patch.object(timeutils, 'utcnow')
    def test_node_states(self, mock_utcnow):
        fake_state = 'fake-state'
        fake_error = 'fake-error'
        test_time = datetime.datetime(2000, 1, 1, 0, 0)
        mock_utcnow.return_value = test_time
        node = obj_utils.create_test_node(self.context,
                                          power_state=fake_state,
                                          target_power_state=fake_state,
                                          provision_state=fake_state,
                                          target_provision_state=fake_state,
                                          provision_updated_at=test_time,
                                          last_error=fake_error)
        data = self.get_json('/nodes/%s/states' % node.uuid)
        self.assertEqual(fake_state, data['power_state'])
        self.assertEqual(fake_state, data['target_power_state'])
        self.assertEqual(fake_state, data['provision_state'])
        self.assertEqual(fake_state, data['target_provision_state'])
        prov_up_at = timeutils.parse_isotime(
                        data['provision_updated_at']).replace(tzinfo=None)
        self.assertEqual(test_time, prov_up_at)
        self.assertEqual(fake_error, data['last_error'])
        self.assertFalse(data['console_enabled'])

    @mock.patch.object(timeutils, 'utcnow')
    def test_node_states_by_name(self, mock_utcnow):
        fake_state = 'fake-state'
        fake_error = 'fake-error'
        test_time = datetime.datetime(1971, 3, 9, 0, 0)
        mock_utcnow.return_value = test_time
        node = obj_utils.create_test_node(self.context,
                                          name='eggs',
                                          power_state=fake_state,
                                          target_power_state=fake_state,
                                          provision_state=fake_state,
                                          target_provision_state=fake_state,
                                          provision_updated_at=test_time,
                                          last_error=fake_error)
        data = self.get_json('/nodes/%s/states' % node.name,
                headers={api_base.Version.string: "1.5"})
        self.assertEqual(fake_state, data['power_state'])
        self.assertEqual(fake_state, data['target_power_state'])
        self.assertEqual(fake_state, data['provision_state'])
        self.assertEqual(fake_state, data['target_provision_state'])
        prov_up_at = timeutils.parse_isotime(
                        data['provision_updated_at']).replace(tzinfo=None)
        self.assertEqual(test_time, prov_up_at)
        self.assertEqual(fake_error, data['last_error'])
        self.assertFalse(data['console_enabled'])

    def test_node_by_instance_uuid(self):
        node = obj_utils.create_test_node(
            self.context,
            uuid=uuidutils.generate_uuid(),
            instance_uuid=uuidutils.generate_uuid())
        instance_uuid = node.instance_uuid

        data = self.get_json('/nodes?instance_uuid=%s' % instance_uuid,
                headers={api_base.Version.string: "1.5"})

        self.assertThat(data['nodes'], HasLength(1))
        self.assertEqual(node['instance_uuid'],
                         data['nodes'][0]["instance_uuid"])

    def test_node_by_instance_uuid_wrong_uuid(self):
        obj_utils.create_test_node(
            self.context, uuid=uuidutils.generate_uuid(),
            instance_uuid=uuidutils.generate_uuid())
        wrong_uuid = uuidutils.generate_uuid()

        data = self.get_json('/nodes?instance_uuid=%s' % wrong_uuid)

        self.assertThat(data['nodes'], HasLength(0))

    def test_node_by_instance_uuid_invalid_uuid(self):
        response = self.get_json('/nodes?instance_uuid=fake',
                                 expect_errors=True)

        self.assertEqual('application/json', response.content_type)
        self.assertEqual(400, response.status_code)

    def test_associated_nodes_insensitive(self):
        associated_nodes = (self
                            ._create_association_test_nodes()
                            .get('associated'))

        data = self.get_json('/nodes?associated=true')
        data1 = self.get_json('/nodes?associated=True')

        uuids = [n['uuid'] for n in data['nodes']]
        uuids1 = [n['uuid'] for n in data1['nodes']]
        self.assertEqual(sorted(associated_nodes), sorted(uuids1))
        self.assertEqual(sorted(associated_nodes), sorted(uuids))

    def test_associated_nodes_error(self):
        self._create_association_test_nodes()
        response = self.get_json('/nodes?associated=blah', expect_errors=True)
        self.assertEqual('application/json', response.content_type)
        self.assertEqual(400, response.status_code)
        self.assertTrue(response.json['error_message'])

    def test_unassociated_nodes_insensitive(self):
        unassociated_nodes = (self
                              ._create_association_test_nodes()
                              .get('unassociated'))

        data = self.get_json('/nodes?associated=false')
        data1 = self.get_json('/nodes?associated=FALSE')

        uuids = [n['uuid'] for n in data['nodes']]
        uuids1 = [n['uuid'] for n in data1['nodes']]
        self.assertEqual(sorted(unassociated_nodes), sorted(uuids1))
        self.assertEqual(sorted(unassociated_nodes), sorted(uuids))

    def test_unassociated_nodes_with_limit(self):
        unassociated_nodes = (self
                              ._create_association_test_nodes()
                              .get('unassociated'))

        data = self.get_json('/nodes?associated=False&limit=2')

        self.assertThat(data['nodes'], HasLength(2))
        self.assertTrue(data['nodes'][0]['uuid'] in unassociated_nodes)

    def test_next_link_with_association(self):
        self._create_association_test_nodes()
        data = self.get_json('/nodes/?limit=3&associated=True')
        self.assertThat(data['nodes'], HasLength(3))
        self.assertIn('associated=True', data['next'])

    def test_detail_with_association_filter(self):
        associated_nodes = (self
                            ._create_association_test_nodes()
                            .get('associated'))
        data = self.get_json('/nodes/detail?associated=true')
        self.assertIn('driver', data['nodes'][0])
        self.assertEqual(len(associated_nodes), len(data['nodes']))

    def test_next_link_with_association_with_detail(self):
        self._create_association_test_nodes()
        data = self.get_json('/nodes/detail?limit=3&associated=true')
        self.assertThat(data['nodes'], HasLength(3))
        self.assertIn('driver', data['nodes'][0])
        self.assertIn('associated=True', data['next'])

    def test_detail_with_instance_uuid(self):
        node = obj_utils.create_test_node(
            self.context,
            uuid=uuidutils.generate_uuid(),
            instance_uuid=uuidutils.generate_uuid(),
            chassis_id=self.chassis.id)
        instance_uuid = node.instance_uuid

        data = self.get_json('/nodes/detail?instance_uuid=%s' % instance_uuid)

        self.assertEqual(node['instance_uuid'],
                         data['nodes'][0]["instance_uuid"])
        self.assertIn('driver', data['nodes'][0])
        self.assertIn('driver_info', data['nodes'][0])
        self.assertIn('extra', data['nodes'][0])
        self.assertIn('properties', data['nodes'][0])
        self.assertIn('chassis_uuid', data['nodes'][0])
        # never expose the chassis_id
        self.assertNotIn('chassis_id', data['nodes'][0])

    def test_maintenance_nodes(self):
        nodes = []
        for id in range(5):
            node = obj_utils.create_test_node(self.context,
                                              uuid=uuidutils.generate_uuid(),
                                              maintenance=id % 2)
            nodes.append(node)

        data = self.get_json('/nodes?maintenance=true')
        uuids = [n['uuid'] for n in data['nodes']]
        test_uuids_1 = [n.uuid for n in nodes if n.maintenance]
        self.assertEqual(sorted(test_uuids_1), sorted(uuids))

        data = self.get_json('/nodes?maintenance=false')
        uuids = [n['uuid'] for n in data['nodes']]
        test_uuids_0 = [n.uuid for n in nodes if not n.maintenance]
        self.assertEqual(sorted(test_uuids_0), sorted(uuids))

    def test_maintenance_nodes_error(self):
        response = self.get_json('/nodes?associated=true&maintenance=blah',
                                 expect_errors=True)
        self.assertEqual('application/json', response.content_type)
        self.assertEqual(400, response.status_code)
        self.assertTrue(response.json['error_message'])

    def test_maintenance_nodes_associated(self):
        self._create_association_test_nodes()
        node = obj_utils.create_test_node(
            self.context,
            instance_uuid=uuidutils.generate_uuid(),
            maintenance=True)

        data = self.get_json('/nodes?associated=true&maintenance=false')
        uuids = [n['uuid'] for n in data['nodes']]
        self.assertNotIn(node.uuid, uuids)
        data = self.get_json('/nodes?associated=true&maintenance=true')
        uuids = [n['uuid'] for n in data['nodes']]
        self.assertIn(node.uuid, uuids)
        data = self.get_json('/nodes?associated=true&maintenance=TruE')
        uuids = [n['uuid'] for n in data['nodes']]
        self.assertIn(node.uuid, uuids)

    def test_get_console_information(self):
        node = obj_utils.create_test_node(self.context)
        expected_console_info = {'test': 'test-data'}
        expected_data = {'console_enabled': True,
                         'console_info': expected_console_info}
        with mock.patch.object(rpcapi.ConductorAPI,
                               'get_console_information') as mock_gci:
            mock_gci.return_value = expected_console_info
            data = self.get_json('/nodes/%s/states/console' % node.uuid)
            self.assertEqual(expected_data, data)
            mock_gci.assert_called_once_with(mock.ANY, node.uuid, 'test-topic')

    @mock.patch.object(rpcapi.ConductorAPI, 'get_console_information')
    def test_get_console_information_by_name(self, mock_gci):
        node = obj_utils.create_test_node(self.context, name='spam')
        expected_console_info = {'test': 'test-data'}
        expected_data = {'console_enabled': True,
                         'console_info': expected_console_info}
        mock_gci.return_value = expected_console_info
        data = self.get_json('/nodes/%s/states/console' % node.name,
                headers={api_base.Version.string: "1.5"})
        self.assertEqual(expected_data, data)
        mock_gci.assert_called_once_with(mock.ANY, node.uuid, 'test-topic')

    def test_get_console_information_console_disabled(self):
        node = obj_utils.create_test_node(self.context)
        expected_data = {'console_enabled': False,
                         'console_info': None}
        with mock.patch.object(rpcapi.ConductorAPI,
                               'get_console_information') as mock_gci:
            mock_gci.side_effect = exception.NodeConsoleNotEnabled(
                    node=node.uuid)
            data = self.get_json('/nodes/%s/states/console' % node.uuid)
            self.assertEqual(expected_data, data)
            mock_gci.assert_called_once_with(mock.ANY, node.uuid, 'test-topic')

    def test_get_console_information_not_supported(self):
        node = obj_utils.create_test_node(self.context)
        with mock.patch.object(rpcapi.ConductorAPI,
                               'get_console_information') as mock_gci:
            mock_gci.side_effect = exception.UnsupportedDriverExtension(
                                   extension='console', driver='test-driver')
            ret = self.get_json('/nodes/%s/states/console' % node.uuid,
                                expect_errors=True)
            self.assertEqual(400, ret.status_code)
            mock_gci.assert_called_once_with(mock.ANY, node.uuid, 'test-topic')

    @mock.patch.object(rpcapi.ConductorAPI, 'get_boot_device')
    def test_get_boot_device(self, mock_gbd):
        node = obj_utils.create_test_node(self.context)
        expected_data = {'boot_device': boot_devices.PXE, 'persistent': True}
        mock_gbd.return_value = expected_data
        data = self.get_json('/nodes/%s/management/boot_device' % node.uuid)
        self.assertEqual(expected_data, data)
        mock_gbd.assert_called_once_with(mock.ANY, node.uuid, 'test-topic')

    @mock.patch.object(rpcapi.ConductorAPI, 'get_boot_device')
    def test_get_boot_device_by_name(self, mock_gbd):
        node = obj_utils.create_test_node(self.context, name='spam')
        expected_data = {'boot_device': boot_devices.PXE, 'persistent': True}
        mock_gbd.return_value = expected_data
        data = self.get_json('/nodes/%s/management/boot_device' % node.name,
                headers={api_base.Version.string: "1.5"})
        self.assertEqual(expected_data, data)
        mock_gbd.assert_called_once_with(mock.ANY, node.uuid, 'test-topic')

    @mock.patch.object(rpcapi.ConductorAPI, 'get_boot_device')
    def test_get_boot_device_iface_not_supported(self, mock_gbd):
        node = obj_utils.create_test_node(self.context)
        mock_gbd.side_effect = exception.UnsupportedDriverExtension(
                                  extension='management', driver='test-driver')
        ret = self.get_json('/nodes/%s/management/boot_device' % node.uuid,
                            expect_errors=True)
        self.assertEqual(400, ret.status_code)
        self.assertTrue(ret.json['error_message'])
        mock_gbd.assert_called_once_with(mock.ANY, node.uuid, 'test-topic')

    @mock.patch.object(rpcapi.ConductorAPI, 'get_supported_boot_devices')
    def test_get_supported_boot_devices(self, mock_gsbd):
        mock_gsbd.return_value = [boot_devices.PXE]
        node = obj_utils.create_test_node(self.context)
        data = self.get_json('/nodes/%s/management/boot_device/supported'
                             % node.uuid)
        expected_data = {'supported_boot_devices': [boot_devices.PXE]}
        self.assertEqual(expected_data, data)
        mock_gsbd.assert_called_once_with(mock.ANY, node.uuid, 'test-topic')

    @mock.patch.object(rpcapi.ConductorAPI, 'get_supported_boot_devices')
    def test_get_supported_boot_devices_by_name(self, mock_gsbd):
        mock_gsbd.return_value = [boot_devices.PXE]
        node = obj_utils.create_test_node(self.context, name='spam')
        data = self.get_json(
                '/nodes/%s/management/boot_device/supported' % node.name,
                headers={api_base.Version.string: "1.5"})
        expected_data = {'supported_boot_devices': [boot_devices.PXE]}
        self.assertEqual(expected_data, data)
        mock_gsbd.assert_called_once_with(mock.ANY, node.uuid, 'test-topic')

    @mock.patch.object(rpcapi.ConductorAPI, 'get_supported_boot_devices')
    def test_get_supported_boot_devices_iface_not_supported(self, mock_gsbd):
        node = obj_utils.create_test_node(self.context)
        mock_gsbd.side_effect = exception.UnsupportedDriverExtension(
                                  extension='management', driver='test-driver')
        ret = self.get_json('/nodes/%s/management/boot_device/supported' %
                            node.uuid, expect_errors=True)
        self.assertEqual(400, ret.status_code)
        self.assertTrue(ret.json['error_message'])
        mock_gsbd.assert_called_once_with(mock.ANY, node.uuid, 'test-topic')

    @mock.patch.object(rpcapi.ConductorAPI, 'validate_driver_interfaces')
    def test_validate_by_uuid_using_deprecated_interface(self, mock_vdi):
        # Note(mrda): The 'node_uuid' interface is deprecated in favour
        # of the 'node' interface
        node = obj_utils.create_test_node(self.context)
        self.get_json('/nodes/validate?node_uuid=%s' % node.uuid)
        mock_vdi.assert_called_once_with(mock.ANY, node.uuid, 'test-topic')

    @mock.patch.object(rpcapi.ConductorAPI, 'validate_driver_interfaces')
    def test_validate_by_uuid(self, mock_vdi):
        node = obj_utils.create_test_node(self.context)
        self.get_json('/nodes/validate?node=%s' % node.uuid,
                      headers={api_base.Version.string: "1.5"})
        mock_vdi.assert_called_once_with(mock.ANY, node.uuid, 'test-topic')

    @mock.patch.object(rpcapi.ConductorAPI, 'validate_driver_interfaces')
    def test_validate_by_name_unsupported(self, mock_vdi):
        node = obj_utils.create_test_node(self.context, name='spam')
        ret = self.get_json('/nodes/validate?node=%s' % node.name,
                            expect_errors=True)
        self.assertEqual(406, ret.status_code)
        self.assertFalse(mock_vdi.called)

    @mock.patch.object(rpcapi.ConductorAPI, 'validate_driver_interfaces')
    def test_validate_by_name(self, mock_vdi):
        node = obj_utils.create_test_node(self.context, name='spam')
        self.get_json('/nodes/validate?node=%s' % node.name,
                headers={api_base.Version.string: "1.5"})
        # note that this should be node.uuid here as we get that from the
        # rpc_node lookup and pass that downwards
        mock_vdi.assert_called_once_with(mock.ANY, node.uuid, 'test-topic')


class TestPatch(test_api_base.FunctionalTest):

    def setUp(self):
        super(TestPatch, self).setUp()
        self.chassis = obj_utils.create_test_chassis(self.context)
        self.node = obj_utils.create_test_node(self.context, name='node-57',
                                               chassis_id=self.chassis.id)
        self.node_no_name = obj_utils.create_test_node(self.context,
            uuid='deadbeef-0000-1111-2222-333333333333',
            chassis_id=self.chassis.id)
        p = mock.patch.object(rpcapi.ConductorAPI, 'get_topic_for')
        self.mock_gtf = p.start()
        self.mock_gtf.return_value = 'test-topic'
        self.addCleanup(p.stop)
        p = mock.patch.object(rpcapi.ConductorAPI, 'update_node')
        self.mock_update_node = p.start()
        self.addCleanup(p.stop)
        p = mock.patch.object(rpcapi.ConductorAPI, 'change_node_power_state')
        self.mock_cnps = p.start()
        self.addCleanup(p.stop)

    def test_update_ok(self):
        self.mock_update_node.return_value = self.node
        (self
         .mock_update_node
         .return_value
         .updated_at) = "2013-12-03T06:20:41.184720+00:00"
        response = self.patch_json('/nodes/%s' % self.node.uuid,
                             [{'path': '/instance_uuid',
                               'value': 'aaaaaaaa-1111-bbbb-2222-cccccccccccc',
                               'op': 'replace'}])
        self.assertEqual('application/json', response.content_type)
        self.assertEqual(200, response.status_code)
        self.assertEqual(self.mock_update_node.return_value.updated_at,
                         timeutils.parse_isotime(response.json['updated_at']))
        self.mock_update_node.assert_called_once_with(
                mock.ANY, mock.ANY, 'test-topic')

    def test_update_by_name_unsupported(self):
        self.mock_update_node.return_value = self.node
        (self
         .mock_update_node
         .return_value
         .updated_at) = "2013-12-03T06:20:41.184720+00:00"
        response = self.patch_json(
                '/nodes/%s' % self.node.name,
                [{'path': '/instance_uuid',
                  'value': 'aaaaaaaa-1111-bbbb-2222-cccccccccccc',
                  'op': 'replace'}],
                expect_errors=True)
        self.assertEqual(404, response.status_code)
        self.assertFalse(self.mock_update_node.called)

    def test_update_ok_by_name(self):
        self.mock_update_node.return_value = self.node
        (self
         .mock_update_node
         .return_value
         .updated_at) = "2013-12-03T06:20:41.184720+00:00"
        response = self.patch_json(
                '/nodes/%s' % self.node.name,
                [{'path': '/instance_uuid',
                  'value': 'aaaaaaaa-1111-bbbb-2222-cccccccccccc',
                  'op': 'replace'}],
                headers={api_base.Version.string: "1.5"})
        self.assertEqual('application/json', response.content_type)
        self.assertEqual(200, response.status_code)
        self.assertEqual(self.mock_update_node.return_value.updated_at,
                         timeutils.parse_isotime(response.json['updated_at']))
        self.mock_update_node.assert_called_once_with(
                mock.ANY, mock.ANY, 'test-topic')

    def test_update_state(self):
        response = self.patch_json('/nodes/%s' % self.node.uuid,
                                   [{'power_state': 'new state'}],
                                   expect_errors=True)
        self.assertEqual('application/json', response.content_type)
        self.assertEqual(400, response.status_code)
        self.assertTrue(response.json['error_message'])

    def test_update_fails_bad_driver_info(self):
        fake_err = 'Fake Error Message'
        self.mock_update_node.side_effect = exception.InvalidParameterValue(
                                                fake_err)

        response = self.patch_json('/nodes/%s' % self.node.uuid,
                                   [{'path': '/driver_info/this',
                                     'value': 'foo',
                                     'op': 'add'},
                                    {'path': '/driver_info/that',
                                     'value': 'bar',
                                     'op': 'add'}],
                                   expect_errors=True)
        self.assertEqual('application/json', response.content_type)
        self.assertEqual(400, response.status_code)

        self.mock_update_node.assert_called_once_with(
                mock.ANY, mock.ANY, 'test-topic')

    def test_update_fails_bad_driver(self):
        self.mock_gtf.side_effect = exception.NoValidHost('Fake Error')

        response = self.patch_json('/nodes/%s' % self.node.uuid,
                                   [{'path': '/driver',
                                     'value': 'bad-driver',
                                     'op': 'replace'}],
                                   expect_errors=True)

        self.assertEqual('application/json', response.content_type)
        self.assertEqual(400, response.status_code)

    def test_update_fails_bad_state(self):
        fake_err = 'Fake Power State'
        self.mock_update_node.side_effect = exception.NodeInWrongPowerState(
                    node=self.node.uuid, pstate=fake_err)

        response = self.patch_json('/nodes/%s' % self.node.uuid,
                             [{'path': '/instance_uuid',
                               'value': 'aaaaaaaa-1111-bbbb-2222-cccccccccccc',
                               'op': 'replace'}],
                                expect_errors=True)
        self.assertEqual('application/json', response.content_type)
        self.assertEqual(409, response.status_code)

        self.mock_update_node.assert_called_once_with(
                mock.ANY, mock.ANY, 'test-topic')

    def test_add_ok(self):
        self.mock_update_node.return_value = self.node

        response = self.patch_json('/nodes/%s' % self.node.uuid,
                                   [{'path': '/extra/foo',
                                     'value': 'bar',
                                     'op': 'add'}])
        self.assertEqual('application/json', response.content_type)
        self.assertEqual(200, response.status_code)

        self.mock_update_node.assert_called_once_with(
                mock.ANY, mock.ANY, 'test-topic')

    def test_add_root(self):
        self.mock_update_node.return_value = self.node
        response = self.patch_json('/nodes/%s' % self.node.uuid,
                             [{'path': '/instance_uuid',
                               'value': 'aaaaaaaa-1111-bbbb-2222-cccccccccccc',
                               'op': 'add'}])
        self.assertEqual('application/json', response.content_type)
        self.assertEqual(200, response.status_code)
        self.mock_update_node.assert_called_once_with(
                mock.ANY, mock.ANY, 'test-topic')

    def test_add_root_non_existent(self):
        response = self.patch_json('/nodes/%s' % self.node.uuid,
                               [{'path': '/foo', 'value': 'bar', 'op': 'add'}],
                               expect_errors=True)
        self.assertEqual('application/json', response.content_type)
        self.assertEqual(400, response.status_code)
        self.assertTrue(response.json['error_message'])

    def test_remove_ok(self):
        self.mock_update_node.return_value = self.node

        response = self.patch_json('/nodes/%s' % self.node.uuid,
                                   [{'path': '/extra',
                                     'op': 'remove'}])
        self.assertEqual('application/json', response.content_type)
        self.assertEqual(200, response.status_code)

        self.mock_update_node.assert_called_once_with(
                mock.ANY, mock.ANY, 'test-topic')

    def test_remove_non_existent_property_fail(self):
        response = self.patch_json('/nodes/%s' % self.node.uuid,
                             [{'path': '/extra/non-existent', 'op': 'remove'}],
                             expect_errors=True)
        self.assertEqual('application/json', response.content_type)
        self.assertEqual(400, response.status_code)
        self.assertTrue(response.json['error_message'])

    def test_update_state_in_progress(self):
        node = obj_utils.create_test_node(self.context,
                                          uuid=uuidutils.generate_uuid(),
                                          target_power_state=states.POWER_OFF)
        response = self.patch_json('/nodes/%s' % node.uuid,
                                   [{'path': '/extra/foo', 'value': 'bar',
                                     'op': 'add'}], expect_errors=True)
        self.assertEqual('application/json', response.content_type)
        self.assertEqual(409, response.status_code)
        self.assertTrue(response.json['error_message'])

    def test_add_state_in_deployfail(self):
        node = obj_utils.create_test_node(self.context,
                                          uuid=uuidutils.generate_uuid(),
                                          provision_state=states.DEPLOYFAIL,
                                          target_provision_state=states.ACTIVE)
        self.mock_update_node.return_value = node
        response = self.patch_json('/nodes/%s' % node.uuid,
                                   [{'path': '/extra/foo', 'value': 'bar',
                                     'op': 'add'}])
        self.assertEqual('application/json', response.content_type)
        self.assertEqual(200, response.status_code)
        self.mock_update_node.assert_called_once_with(
                mock.ANY, mock.ANY, 'test-topic')

    def test_patch_ports_subresource(self):
        response = self.patch_json('/nodes/%s/ports' % self.node.uuid,
                                   [{'path': '/extra/foo', 'value': 'bar',
                                     'op': 'add'}], expect_errors=True)
        self.assertEqual(403, response.status_int)

    def test_remove_uuid(self):
        response = self.patch_json('/nodes/%s' % self.node.uuid,
                                   [{'path': '/uuid', 'op': 'remove'}],
                                   expect_errors=True)
        self.assertEqual('application/json', response.content_type)
        self.assertEqual(400, response.status_code)
        self.assertTrue(response.json['error_message'])

    def test_remove_instance_uuid_cleaning(self):
        node = obj_utils.create_test_node(
            self.context,
            uuid=uuidutils.generate_uuid(),
            provision_state=states.CLEANING,
            target_provision_state=states.AVAILABLE)
        self.mock_update_node.return_value = node
        response = self.patch_json('/nodes/%s' % node.uuid,
                                   [{'op': 'remove',
                                     'path': '/instance_uuid'}])
        self.assertEqual('application/json', response.content_type)
        self.assertEqual(200, response.status_code)
        self.mock_update_node.assert_called_once_with(
                mock.ANY, mock.ANY, 'test-topic')

    def test_add_state_in_cleaning(self):
        node = obj_utils.create_test_node(
            self.context,
            uuid=uuidutils.generate_uuid(),
            provision_state=states.CLEANING,
            target_provision_state=states.AVAILABLE)
        self.mock_update_node.return_value = node
        response = self.patch_json('/nodes/%s' % node.uuid,
                                   [{'path': '/extra/foo', 'value': 'bar',
                                     'op': 'add'}], expect_errors=True)
        self.assertEqual('application/json', response.content_type)
        self.assertEqual(409, response.status_code)
        self.assertTrue(response.json['error_message'])

    def test_remove_mandatory_field(self):
        response = self.patch_json('/nodes/%s' % self.node.uuid,
                                   [{'path': '/driver', 'op': 'remove'}],
                                   expect_errors=True)
        self.assertEqual('application/json', response.content_type)
        self.assertEqual(400, response.status_code)
        self.assertTrue(response.json['error_message'])

    def test_replace_chassis_uuid(self):
        self.mock_update_node.return_value = self.node
        response = self.patch_json('/nodes/%s' % self.node.uuid,
                             [{'path': '/chassis_uuid',
                               'value': self.chassis.uuid,
                               'op': 'replace'}])
        self.assertEqual('application/json', response.content_type)
        self.assertEqual(200, response.status_code)

    def test_add_chassis_uuid(self):
        self.mock_update_node.return_value = self.node
        response = self.patch_json('/nodes/%s' % self.node.uuid,
                             [{'path': '/chassis_uuid',
                               'value': self.chassis.uuid,
                               'op': 'add'}])
        self.assertEqual('application/json', response.content_type)
        self.assertEqual(200, response.status_code)

    def test_add_chassis_id(self):
        response = self.patch_json('/nodes/%s' % self.node.uuid,
                             [{'path': '/chassis_id',
                               'value': '1',
                               'op': 'add'}],
                               expect_errors=True)
        self.assertEqual('application/json', response.content_type)
        self.assertEqual(400, response.status_code)
        self.assertTrue(response.json['error_message'])

    def test_replace_chassis_id(self):
        response = self.patch_json('/nodes/%s' % self.node.uuid,
                             [{'path': '/chassis_id',
                               'value': '1',
                               'op': 'replace'}],
                               expect_errors=True)
        self.assertEqual('application/json', response.content_type)
        self.assertEqual(400, response.status_code)
        self.assertTrue(response.json['error_message'])

    def test_remove_chassis_id(self):
        response = self.patch_json('/nodes/%s' % self.node.uuid,
                             [{'path': '/chassis_id',
                               'op': 'remove'}],
                               expect_errors=True)
        self.assertEqual('application/json', response.content_type)
        self.assertEqual(400, response.status_code)
        self.assertTrue(response.json['error_message'])

    def test_replace_non_existent_chassis_uuid(self):
        response = self.patch_json('/nodes/%s' % self.node.uuid,
                             [{'path': '/chassis_uuid',
                               'value': 'eeeeeeee-dddd-cccc-bbbb-aaaaaaaaaaaa',
                               'op': 'replace'}], expect_errors=True)
        self.assertEqual('application/json', response.content_type)
        self.assertEqual(400, response.status_code)
        self.assertTrue(response.json['error_message'])

    def test_remove_internal_field(self):
        response = self.patch_json('/nodes/%s' % self.node.uuid,
                                   [{'path': '/last_error', 'op': 'remove'}],
                                   expect_errors=True)
        self.assertEqual('application/json', response.content_type)
        self.assertEqual(400, response.status_code)
        self.assertTrue(response.json['error_message'])

    def test_replace_internal_field(self):
        response = self.patch_json('/nodes/%s' % self.node.uuid,
                                   [{'path': '/power_state', 'op': 'replace',
                                     'value': 'fake-state'}],
                                   expect_errors=True)
        self.assertEqual('application/json', response.content_type)
        self.assertEqual(400, response.status_code)
        self.assertTrue(response.json['error_message'])

    def test_replace_maintenance(self):
        self.mock_update_node.return_value = self.node

        response = self.patch_json('/nodes/%s' % self.node.uuid,
                                   [{'path': '/maintenance', 'op': 'replace',
                                     'value': 'true'}])
        self.assertEqual('application/json', response.content_type)
        self.assertEqual(200, response.status_code)

        self.mock_update_node.assert_called_once_with(
                mock.ANY, mock.ANY, 'test-topic')

    def test_replace_maintenance_by_name(self):
        self.mock_update_node.return_value = self.node

        response = self.patch_json(
                '/nodes/%s' % self.node.name,
                [{'path': '/maintenance', 'op': 'replace',
                  'value': 'true'}],
                headers={api_base.Version.string: "1.5"})
        self.assertEqual('application/json', response.content_type)
        self.assertEqual(200, response.status_code)

        self.mock_update_node.assert_called_once_with(
                mock.ANY, mock.ANY, 'test-topic')

    def test_replace_consoled_enabled(self):
        response = self.patch_json('/nodes/%s' % self.node.uuid,
                                   [{'path': '/console_enabled',
                                     'op': 'replace', 'value': True}],
                                   expect_errors=True)
        self.assertEqual('application/json', response.content_type)
        self.assertEqual(400, response.status_code)
        self.assertTrue(response.json['error_message'])

    def test_replace_provision_updated_at(self):
        test_time = '2000-01-01 00:00:00'
        response = self.patch_json('/nodes/%s' % self.node.uuid,
                                   [{'path': '/provision_updated_at',
                                     'op': 'replace', 'value': test_time}],
                                   expect_errors=True)
        self.assertEqual('application/json', response.content_type)
        self.assertEqual(400, response.status_code)
        self.assertTrue(response.json['error_message'])

    def test_patch_add_name_ok(self):
        self.mock_update_node.return_value = self.node_no_name
        test_name = 'guido-van-rossum'
        response = self.patch_json('/nodes/%s' % self.node_no_name.uuid,
                                   [{'path': '/name',
                                     'op': 'add',
                                     'value': test_name}],
                                   headers={api_base.Version.string: "1.5"})
        self.assertEqual('application/json', response.content_type)
        self.assertEqual(200, response.status_code)

    def test_patch_add_name_invalid(self):
        self.mock_update_node.return_value = self.node_no_name
        test_name = 'I-AM-INVALID'
        response = self.patch_json('/nodes/%s' % self.node_no_name.uuid,
                                   [{'path': '/name',
                                     'op': 'add',
                                     'value': test_name}],
                                   headers={api_base.Version.string: "1.5"},
                                   expect_errors=True)
        self.assertEqual('application/json', response.content_type)
        self.assertEqual(400, response.status_code)
        self.assertTrue(response.json['error_message'])

    def test_patch_name_replace_ok(self):
        self.mock_update_node.return_value = self.node
        test_name = 'guido-van-rossum'
        response = self.patch_json('/nodes/%s' % self.node.uuid,
                                   [{'path': '/name',
                                     'op': 'replace',
                                     'value': test_name}],
                                   headers={api_base.Version.string: "1.5"})
        self.assertEqual('application/json', response.content_type)
        self.assertEqual(200, response.status_code)

    def test_patch_add_replace_invalid(self):
        self.mock_update_node.return_value = self.node_no_name
        test_name = 'Guido Van Error'
        response = self.patch_json('/nodes/%s' % self.node.uuid,
                                   [{'path': '/name',
                                     'op': 'replace',
                                     'value': test_name}],
                                   headers={api_base.Version.string: "1.5"},
                                   expect_errors=True)
        self.assertEqual('application/json', response.content_type)
        self.assertEqual(400, response.status_code)
        self.assertTrue(response.json['error_message'])

    def test_patch_duplicate_name(self):
        node = obj_utils.create_test_node(self.context,
                                          uuid=uuidutils.generate_uuid())
        test_name = "this-is-my-node"
        self.mock_update_node.side_effect = exception.DuplicateName(test_name)
        response = self.patch_json('/nodes/%s' % node.uuid,
                                   [{'path': '/name',
                                     'op': 'replace',
                                     'value': test_name}],
                                   headers={api_base.Version.string: "1.5"},
                                   expect_errors=True)
        self.assertEqual('application/json', response.content_type)
        self.assertEqual(409, response.status_code)
        self.assertTrue(response.json['error_message'])

    @mock.patch.object(api_utils, 'get_rpc_node')
    def test_patch_update_drive_console_enabled(self, mock_rpc_node):
        self.node.console_enabled = True
        mock_rpc_node.return_value = self.node

        response = self.patch_json('/nodes/%s' % self.node.uuid,
                                   [{'path': '/driver',
                                     'value': 'foo',
                                     'op': 'add'}],
                                   expect_errors=True)
        mock_rpc_node.assert_called_once_with(self.node.uuid)
        self.assertEqual('application/json', response.content_type)
        self.assertEqual(409, response.status_code)
        self.assertTrue(response.json['error_message'])


class TestPost(test_api_base.FunctionalTest):

    def setUp(self):
        super(TestPost, self).setUp()
        self.chassis = obj_utils.create_test_chassis(self.context)
        p = mock.patch.object(rpcapi.ConductorAPI, 'get_topic_for')
        self.mock_gtf = p.start()
        self.mock_gtf.return_value = 'test-topic'
        self.addCleanup(p.stop)

    @mock.patch.object(timeutils, 'utcnow')
    def test_create_node(self, mock_utcnow):
        ndict = test_api_utils.post_get_test_node()
        test_time = datetime.datetime(2000, 1, 1, 0, 0)
        mock_utcnow.return_value = test_time
        response = self.post_json('/nodes', ndict)
        self.assertEqual(201, response.status_int)
        result = self.get_json('/nodes/%s' % ndict['uuid'])
        self.assertEqual(ndict['uuid'], result['uuid'])
        self.assertFalse(result['updated_at'])
        return_created_at = timeutils.parse_isotime(
                result['created_at']).replace(tzinfo=None)
        self.assertEqual(test_time, return_created_at)
        # Check location header
        self.assertIsNotNone(response.location)
        expected_location = '/v1/nodes/%s' % ndict['uuid']
        self.assertEqual(urlparse.urlparse(response.location).path,
                         expected_location)

    def test_create_node_doesnt_contain_id(self):
        # FIXME(comstud): I'd like to make this test not use the
        # dbapi, however, no matter what I do when trying to mock
        # Node.create(), the API fails to convert the objects.Node
        # into the API Node object correctly (it leaves all fields
        # as Unset).
        with mock.patch.object(self.dbapi, 'create_node',
                               wraps=self.dbapi.create_node) as cn_mock:
            ndict = test_api_utils.post_get_test_node(extra={'foo': 123})
            self.post_json('/nodes', ndict)
            result = self.get_json('/nodes/%s' % ndict['uuid'])
            self.assertEqual(ndict['extra'], result['extra'])
            cn_mock.assert_called_once_with(mock.ANY)
            # Check that 'id' is not in first arg of positional args
            self.assertNotIn('id', cn_mock.call_args[0][0])

    def _test_jsontype_attributes(self, attr_name):
        kwargs = {attr_name: {'str': 'foo', 'int': 123, 'float': 0.1,
                              'bool': True, 'list': [1, 2], 'none': None,
                              'dict': {'cat': 'meow'}}}
        ndict = test_api_utils.post_get_test_node(**kwargs)
        self.post_json('/nodes', ndict)
        result = self.get_json('/nodes/%s' % ndict['uuid'])
        self.assertEqual(ndict[attr_name], result[attr_name])

    def test_create_node_valid_extra(self):
        self._test_jsontype_attributes('extra')

    def test_create_node_valid_properties(self):
        self._test_jsontype_attributes('properties')

    def test_create_node_valid_driver_info(self):
        self._test_jsontype_attributes('driver_info')

    def test_create_node_valid_instance_info(self):
        self._test_jsontype_attributes('instance_info')

    def _test_vendor_passthru_ok(self, mock_vendor, return_value=None,
                                 is_async=True):
        expected_status = 202 if is_async else 200
        expected_return_value = json.dumps(return_value)
        if six.PY3:
            expected_return_value = expected_return_value.encode('utf-8')

        node = obj_utils.create_test_node(self.context)
        info = {'foo': 'bar'}
        mock_vendor.return_value = (return_value, is_async)
        response = self.post_json('/nodes/%s/vendor_passthru/test' % node.uuid,
                                  info)
        mock_vendor.assert_called_once_with(
                mock.ANY, node.uuid, 'test', 'POST', info, 'test-topic')
        self.assertEqual(expected_return_value, response.body)
        self.assertEqual(expected_status, response.status_code)

    def _test_vendor_passthru_ok_by_name(self, mock_vendor, return_value=None,
                                         is_async=True):
        expected_status = 202 if is_async else 200
        expected_return_value = json.dumps(return_value)
        if six.PY3:
            expected_return_value = expected_return_value.encode('utf-8')

        node = obj_utils.create_test_node(self.context, name='node-109')
        info = {'foo': 'bar'}
        mock_vendor.return_value = (return_value, is_async)
        response = self.post_json('/nodes/%s/vendor_passthru/test' % node.name,
                                  info,
                                  headers={api_base.Version.string: "1.5"})
        mock_vendor.assert_called_once_with(
                mock.ANY, node.uuid, 'test', 'POST', info, 'test-topic')
        self.assertEqual(expected_return_value, response.body)
        self.assertEqual(expected_status, response.status_code)

    @mock.patch.object(rpcapi.ConductorAPI, 'vendor_passthru')
    def test_vendor_passthru_async(self, mock_vendor):
        self._test_vendor_passthru_ok(mock_vendor)

    @mock.patch.object(rpcapi.ConductorAPI, 'vendor_passthru')
    def test_vendor_passthru_sync(self, mock_vendor):
        return_value = {'cat': 'meow'}
        self._test_vendor_passthru_ok(mock_vendor, return_value=return_value,
                                      is_async=False)

    @mock.patch.object(rpcapi.ConductorAPI, 'vendor_passthru')
    def test_vendor_passthru_put(self, mocked_vendor_passthru):
        node = obj_utils.create_test_node(self.context)
        return_value = (None, 'async')
        mocked_vendor_passthru.return_value = return_value
        response = self.put_json(
            '/nodes/%s/vendor_passthru/do_test' % node.uuid,
            {'test_key': 'test_value'})
        self.assertEqual(202, response.status_int)
        self.assertEqual(return_value[0], response.json)

    @mock.patch.object(rpcapi.ConductorAPI, 'vendor_passthru')
    def test_vendor_passthru_by_name(self, mock_vendor):
        self._test_vendor_passthru_ok_by_name(mock_vendor)

    @mock.patch.object(rpcapi.ConductorAPI, 'vendor_passthru')
    def test_vendor_passthru_get(self, mocked_vendor_passthru):
        node = obj_utils.create_test_node(self.context)
        return_value = ('foo', 'sync')
        mocked_vendor_passthru.return_value = return_value
        response = self.get_json(
            '/nodes/%s/vendor_passthru/do_test' % node.uuid)
        self.assertEqual(return_value[0], response)

    @mock.patch.object(rpcapi.ConductorAPI, 'vendor_passthru')
    def test_vendor_passthru_delete(self, mock_vendor_passthru):
        node = obj_utils.create_test_node(self.context)
        return_value = (None, 'async')
        mock_vendor_passthru.return_value = return_value
        response = self.delete(
            '/nodes/%s/vendor_passthru/do_test' % node.uuid)
        self.assertEqual(202, response.status_int)
        self.assertEqual(return_value[0], response.json)

    def test_vendor_passthru_no_such_method(self):
        node = obj_utils.create_test_node(self.context)
        uuid = node.uuid
        info = {'foo': 'bar'}

        with mock.patch.object(
                rpcapi.ConductorAPI, 'vendor_passthru') as mock_vendor:
            mock_vendor.side_effect = exception.UnsupportedDriverExtension(
                **{'driver': node.driver, 'node': uuid, 'extension': 'test'})
            response = self.post_json('/nodes/%s/vendor_passthru/test' % uuid,
                                      info, expect_errors=True)
            mock_vendor.assert_called_once_with(
                    mock.ANY, uuid, 'test', 'POST', info, 'test-topic')
            self.assertEqual(400, response.status_code)

    def test_vendor_passthru_without_method(self):
        node = obj_utils.create_test_node(self.context)
        response = self.post_json('/nodes/%s/vendor_passthru' % node.uuid,
                                  {'foo': 'bar'}, expect_errors=True)
        self.assertEqual('application/json', response.content_type, )
        self.assertEqual(400, response.status_code)
        self.assertTrue(response.json['error_message'])

    def test_post_ports_subresource(self):
        node = obj_utils.create_test_node(self.context)
        pdict = test_api_utils.port_post_data(node_id=None)
        pdict['node_uuid'] = node.uuid
        response = self.post_json('/nodes/ports', pdict,
                                  expect_errors=True)
        self.assertEqual(403, response.status_int)

    def test_create_node_no_mandatory_field_driver(self):
        ndict = test_api_utils.post_get_test_node()
        del ndict['driver']
        response = self.post_json('/nodes', ndict, expect_errors=True)
        self.assertEqual(400, response.status_int)
        self.assertEqual('application/json', response.content_type)
        self.assertTrue(response.json['error_message'])

    def test_create_node_invalid_driver(self):
        ndict = test_api_utils.post_get_test_node()
        self.mock_gtf.side_effect = exception.NoValidHost('Fake Error')
        response = self.post_json('/nodes', ndict, expect_errors=True)
        self.assertEqual(400, response.status_int)
        self.assertEqual('application/json', response.content_type)
        self.assertTrue(response.json['error_message'])

    def test_create_node_no_chassis_uuid(self):
        ndict = test_api_utils.post_get_test_node()
        del ndict['chassis_uuid']
        response = self.post_json('/nodes', ndict)
        self.assertEqual('application/json', response.content_type)
        self.assertEqual(201, response.status_int)
        # Check location header
        self.assertIsNotNone(response.location)
        expected_location = '/v1/nodes/%s' % ndict['uuid']
        self.assertEqual(urlparse.urlparse(response.location).path,
                         expected_location)

    def test_create_node_with_chassis_uuid(self):
        ndict = test_api_utils.post_get_test_node(
                    chassis_uuid=self.chassis.uuid)
        response = self.post_json('/nodes', ndict)
        self.assertEqual('application/json', response.content_type)
        self.assertEqual(201, response.status_int)
        result = self.get_json('/nodes/%s' % ndict['uuid'])
        self.assertEqual(ndict['chassis_uuid'], result['chassis_uuid'])
        # Check location header
        self.assertIsNotNone(response.location)
        expected_location = '/v1/nodes/%s' % ndict['uuid']
        self.assertEqual(urlparse.urlparse(response.location).path,
                         expected_location)

    def test_create_node_chassis_uuid_not_found(self):
        ndict = test_api_utils.post_get_test_node(
                           chassis_uuid='1a1a1a1a-2b2b-3c3c-4d4d-5e5e5e5e5e5e')
        response = self.post_json('/nodes', ndict, expect_errors=True)
        self.assertEqual('application/json', response.content_type)
        self.assertEqual(400, response.status_int)
        self.assertTrue(response.json['error_message'])

    def test_create_node_with_internal_field(self):
        ndict = test_api_utils.post_get_test_node()
        ndict['reservation'] = 'fake'
        response = self.post_json('/nodes', ndict, expect_errors=True)
        self.assertEqual('application/json', response.content_type)
        self.assertEqual(400, response.status_int)
        self.assertTrue(response.json['error_message'])

    @mock.patch.object(rpcapi.ConductorAPI, 'get_node_vendor_passthru_methods')
    def test_vendor_passthru_methods(self, get_methods_mock):
        return_value = {'foo': 'bar'}
        get_methods_mock.return_value = return_value
        node = obj_utils.create_test_node(self.context)
        path = '/nodes/%s/vendor_passthru/methods' % node.uuid

        data = self.get_json(path)
        self.assertEqual(return_value, data)
        get_methods_mock.assert_called_once_with(mock.ANY, node.uuid,
                                                  topic=mock.ANY)

        # Now let's test the cache: Reset the mock
        get_methods_mock.reset_mock()

        # Call it again
        data = self.get_json(path)
        self.assertEqual(return_value, data)
        # Assert RPC method wasn't called this time
        self.assertFalse(get_methods_mock.called)


class TestDelete(test_api_base.FunctionalTest):

    def setUp(self):
        super(TestDelete, self).setUp()
        p = mock.patch.object(rpcapi.ConductorAPI, 'get_topic_for')
        self.mock_gtf = p.start()
        self.mock_gtf.return_value = 'test-topic'
        self.addCleanup(p.stop)

    @mock.patch.object(rpcapi.ConductorAPI, 'destroy_node')
    def test_delete_node(self, mock_dn):
        node = obj_utils.create_test_node(self.context)
        self.delete('/nodes/%s' % node.uuid)
        mock_dn.assert_called_once_with(mock.ANY, node.uuid, 'test-topic')

    @mock.patch.object(rpcapi.ConductorAPI, 'destroy_node')
    def test_delete_node_by_name_unsupported(self, mock_dn):
        node = obj_utils.create_test_node(self.context, name='foo')
        self.delete('/nodes/%s' % node.name,
                    expect_errors=True)
        self.assertFalse(mock_dn.called)

    @mock.patch.object(rpcapi.ConductorAPI, 'destroy_node')
    def test_delete_node_by_name(self, mock_dn):
        node = obj_utils.create_test_node(self.context, name='foo')
        self.delete('/nodes/%s' % node.name,
                headers={api_base.Version.string: "1.5"})
        mock_dn.assert_called_once_with(mock.ANY, node.uuid, 'test-topic')

    @mock.patch.object(objects.Node, 'get_by_uuid')
    def test_delete_node_not_found(self, mock_gbu):
        node = obj_utils.get_test_node(self.context)
        mock_gbu.side_effect = exception.NodeNotFound(node=node.uuid)

        response = self.delete('/nodes/%s' % node.uuid, expect_errors=True)
        self.assertEqual(404, response.status_int)
        self.assertEqual('application/json', response.content_type)
        self.assertTrue(response.json['error_message'])
        mock_gbu.assert_called_once_with(mock.ANY, node.uuid)

    @mock.patch.object(objects.Node, 'get_by_name')
    def test_delete_node_not_found_by_name_unsupported(self, mock_gbn):
        node = obj_utils.get_test_node(self.context, name='foo')
        mock_gbn.side_effect = exception.NodeNotFound(node=node.name)

        response = self.delete('/nodes/%s' % node.name,
                               expect_errors=True)
        self.assertEqual(404, response.status_int)
        self.assertFalse(mock_gbn.called)

    @mock.patch.object(objects.Node, 'get_by_name')
    def test_delete_node_not_found_by_name(self, mock_gbn):
        node = obj_utils.get_test_node(self.context, name='foo')
        mock_gbn.side_effect = exception.NodeNotFound(node=node.name)

        response = self.delete('/nodes/%s' % node.name,
                headers={api_base.Version.string: "1.5"},
                expect_errors=True)
        self.assertEqual(404, response.status_int)
        self.assertEqual('application/json', response.content_type)
        self.assertTrue(response.json['error_message'])
        mock_gbn.assert_called_once_with(mock.ANY, node.name)

    def test_delete_ports_subresource(self):
        node = obj_utils.create_test_node(self.context)
        response = self.delete('/nodes/%s/ports' % node.uuid,
                               expect_errors=True)
        self.assertEqual(403, response.status_int)

    @mock.patch.object(rpcapi.ConductorAPI, 'destroy_node')
    def test_delete_associated(self, mock_dn):
        node = obj_utils.create_test_node(
                self.context,
                instance_uuid='aaaaaaaa-1111-bbbb-2222-cccccccccccc')
        mock_dn.side_effect = exception.NodeAssociated(node=node.uuid,
                                                   instance=node.instance_uuid)

        response = self.delete('/nodes/%s' % node.uuid, expect_errors=True)
        self.assertEqual(409, response.status_int)
        mock_dn.assert_called_once_with(mock.ANY, node.uuid, 'test-topic')

    @mock.patch.object(objects.Node, 'get_by_uuid')
    @mock.patch.object(rpcapi.ConductorAPI, 'update_node')
    def test_delete_node_maintenance_mode(self, mock_update, mock_get):
        node = obj_utils.create_test_node(self.context, maintenance=True,
                                          maintenance_reason='blah')
        mock_get.return_value = node
        response = self.delete('/nodes/%s/maintenance' % node.uuid)
        self.assertEqual(202, response.status_int)
        self.assertEqual(b'', response.body)
        self.assertEqual(False, node.maintenance)
        self.assertEqual(None, node.maintenance_reason)
        mock_get.assert_called_once_with(mock.ANY, node.uuid)
        mock_update.assert_called_once_with(mock.ANY, mock.ANY,
                                            topic='test-topic')

    @mock.patch.object(objects.Node, 'get_by_name')
    @mock.patch.object(rpcapi.ConductorAPI, 'update_node')
    def test_delete_node_maintenance_mode_by_name(self, mock_update,
                                                  mock_get):
        node = obj_utils.create_test_node(self.context, maintenance=True,
                                          maintenance_reason='blah',
                                          name='foo')
        mock_get.return_value = node
        response = self.delete('/nodes/%s/maintenance' % node.name,
                headers={api_base.Version.string: "1.5"})
        self.assertEqual(202, response.status_int)
        self.assertEqual(b'', response.body)
        self.assertEqual(False, node.maintenance)
        self.assertEqual(None, node.maintenance_reason)
        mock_get.assert_called_once_with(mock.ANY, node.name)
        mock_update.assert_called_once_with(mock.ANY, mock.ANY,
                                            topic='test-topic')


class TestPut(test_api_base.FunctionalTest):

    def setUp(self):
        super(TestPut, self).setUp()
        self.node = obj_utils.create_test_node(self.context,
                provision_state=states.AVAILABLE, name='node-39')
        p = mock.patch.object(rpcapi.ConductorAPI, 'get_topic_for')
        self.mock_gtf = p.start()
        self.mock_gtf.return_value = 'test-topic'
        self.addCleanup(p.stop)
        p = mock.patch.object(rpcapi.ConductorAPI, 'change_node_power_state')
        self.mock_cnps = p.start()
        self.addCleanup(p.stop)
        p = mock.patch.object(rpcapi.ConductorAPI, 'do_node_deploy')
        self.mock_dnd = p.start()
        self.addCleanup(p.stop)
        p = mock.patch.object(rpcapi.ConductorAPI, 'do_node_tear_down')
        self.mock_dntd = p.start()
        self.addCleanup(p.stop)
        p = mock.patch.object(rpcapi.ConductorAPI, 'inspect_hardware')
        self.mock_dnih = p.start()
        self.addCleanup(p.stop)

    def test_power_state(self):
        response = self.put_json('/nodes/%s/states/power' % self.node.uuid,
                                 {'target': states.POWER_ON})
        self.assertEqual(202, response.status_code)
        self.assertEqual(b'', response.body)
        self.mock_cnps.assert_called_once_with(mock.ANY,
                                               self.node.uuid,
                                               states.POWER_ON,
                                               'test-topic')
        # Check location header
        self.assertIsNotNone(response.location)
        expected_location = '/v1/nodes/%s/states' % self.node.uuid
        self.assertEqual(urlparse.urlparse(response.location).path,
                         expected_location)

    def test_power_state_by_name_unsupported(self):
        response = self.put_json('/nodes/%s/states/power' % self.node.name,
                                 {'target': states.POWER_ON},
                                 expect_errors=True)
        self.assertEqual(404, response.status_code)

    def test_power_state_by_name(self):
        response = self.put_json('/nodes/%s/states/power' % self.node.name,
                                 {'target': states.POWER_ON},
                                 headers={api_base.Version.string: "1.5"})
        self.assertEqual(202, response.status_code)
        self.assertEqual(b'', response.body)
        self.mock_cnps.assert_called_once_with(mock.ANY,
                                               self.node.uuid,
                                               states.POWER_ON,
                                               'test-topic')
        # Check location header
        self.assertIsNotNone(response.location)
        expected_location = '/v1/nodes/%s/states' % self.node.name
        self.assertEqual(urlparse.urlparse(response.location).path,
                         expected_location)

    def test_power_invalid_state_request(self):
        ret = self.put_json('/nodes/%s/states/power' % self.node.uuid,
                            {'target': 'not-supported'}, expect_errors=True)
        self.assertEqual(400, ret.status_code)

    def test_power_change_during_cleaning(self):
        self.node.provision_state = states.CLEANING
        self.node.save()
        ret = self.put_json('/nodes/%s/states/power' % self.node.uuid,
                            {'target': states.POWER_OFF}, expect_errors=True)
        self.assertEqual(400, ret.status_code)

    def test_provision_invalid_state_request(self):
        ret = self.put_json('/nodes/%s/states/provision' % self.node.uuid,
                            {'target': 'not-supported'}, expect_errors=True)
        self.assertEqual(400, ret.status_code)

    def test_provision_with_deploy(self):
        ret = self.put_json('/nodes/%s/states/provision' % self.node.uuid,
                            {'target': states.ACTIVE})
        self.assertEqual(202, ret.status_code)
        self.assertEqual(b'', ret.body)
        self.mock_dnd.assert_called_once_with(
                mock.ANY, self.node.uuid, False, None, 'test-topic')
        # Check location header
        self.assertIsNotNone(ret.location)
        expected_location = '/v1/nodes/%s/states' % self.node.uuid
        self.assertEqual(urlparse.urlparse(ret.location).path,
                         expected_location)

    def test_provision_by_name_unsupported(self):
        ret = self.put_json('/nodes/%s/states/provision' % self.node.name,
                            {'target': states.ACTIVE},
                            expect_errors=True)
        self.assertEqual(404, ret.status_code)

    def test_provision_by_name(self):
        ret = self.put_json('/nodes/%s/states/provision' % self.node.name,
                            {'target': states.ACTIVE},
                            headers={api_base.Version.string: "1.5"})
        self.assertEqual(202, ret.status_code)
        self.assertEqual(b'', ret.body)
        self.mock_dnd.assert_called_once_with(
                mock.ANY, self.node.uuid, False, None, 'test-topic')

    def test_provision_with_deploy_configdrive(self):
        ret = self.put_json('/nodes/%s/states/provision' % self.node.uuid,
                            {'target': states.ACTIVE, 'configdrive': 'foo'})
        self.assertEqual(202, ret.status_code)
        self.assertEqual(b'', ret.body)
        self.mock_dnd.assert_called_once_with(
                mock.ANY, self.node.uuid, False, 'foo', 'test-topic')
        # Check location header
        self.assertIsNotNone(ret.location)
        expected_location = '/v1/nodes/%s/states' % self.node.uuid
        self.assertEqual(urlparse.urlparse(ret.location).path,
                         expected_location)

    def test_provision_with_configdrive_not_active(self):
        ret = self.put_json('/nodes/%s/states/provision' % self.node.uuid,
                            {'target': states.DELETED, 'configdrive': 'foo'},
                            expect_errors=True)
        self.assertEqual(400, ret.status_code)

    def test_provision_with_tear_down(self):
        node = self.node
        node.provision_state = states.ACTIVE
        node.target_provision_state = states.NOSTATE
        node.save()
        ret = self.put_json('/nodes/%s/states/provision' % node.uuid,
                            {'target': states.DELETED})
        self.assertEqual(202, ret.status_code)
        self.assertEqual(b'', ret.body)
        self.mock_dntd.assert_called_once_with(
                mock.ANY, node.uuid, 'test-topic')
        # Check location header
        self.assertIsNotNone(ret.location)
        expected_location = '/v1/nodes/%s/states' % node.uuid
        self.assertEqual(urlparse.urlparse(ret.location).path,
                         expected_location)

    def test_provision_already_in_progress(self):
        node = self.node
        node.provision_state = states.DEPLOYING
        node.target_provision_state = states.ACTIVE
        node.reservation = 'fake-host'
        node.save()
        ret = self.put_json('/nodes/%s/states/provision' % node.uuid,
                            {'target': states.ACTIVE},
                            expect_errors=True)
        self.assertEqual(409, ret.status_code)  # Conflict

    def test_provision_with_tear_down_in_progress_deploywait(self):
        node = self.node
        node.provision_state = states.DEPLOYWAIT
        node.target_provision_state = states.ACTIVE
        node.save()
        ret = self.put_json('/nodes/%s/states/provision' % node.uuid,
                            {'target': states.DELETED})
        self.assertEqual(202, ret.status_code)
        self.assertEqual(b'', ret.body)
        self.mock_dntd.assert_called_once_with(
                mock.ANY, node.uuid, 'test-topic')
        # Check location header
        self.assertIsNotNone(ret.location)
        expected_location = '/v1/nodes/%s/states' % node.uuid
        self.assertEqual(urlparse.urlparse(ret.location).path,
                         expected_location)

    # NOTE(deva): this test asserts API funcionality which is not part of
    # the new-ironic-state-machine in Kilo. It is retained for backwards
    # compatibility with Juno.
    # TODO(deva): add a deprecation-warning to the REST result
    # and check for it here.
    def test_provision_with_deploy_after_deployfail(self):
        node = self.node
        node.provision_state = states.DEPLOYFAIL
        node.target_provision_state = states.ACTIVE
        node.save()
        ret = self.put_json('/nodes/%s/states/provision' % node.uuid,
                            {'target': states.ACTIVE})
        self.assertEqual(202, ret.status_code)
        self.assertEqual(b'', ret.body)
        self.mock_dnd.assert_called_once_with(
                mock.ANY, node.uuid, False, None, 'test-topic')
        # Check location header
        self.assertIsNotNone(ret.location)
        expected_location = '/v1/nodes/%s/states' % node.uuid
        self.assertEqual(expected_location,
                         urlparse.urlparse(ret.location).path)

    def test_provision_already_in_state(self):
        self.node.provision_state = states.ACTIVE
        self.node.save()
        ret = self.put_json('/nodes/%s/states/provision' % self.node.uuid,
                            {'target': states.ACTIVE},
                            expect_errors=True)
        self.assertEqual(400, ret.status_code)

    def test_manage_raises_error_before_1_2(self):
        ret = self.put_json('/nodes/%s/states/provision' % self.node.uuid,
                            {'target': states.VERBS['manage']},
                            headers={},
                            expect_errors=True)
        self.assertEqual(406, ret.status_code)

    @mock.patch.object(rpcapi.ConductorAPI, 'do_provisioning_action')
    def test_provide_from_manage(self, mock_dpa):
        self.node.provision_state = states.MANAGEABLE
        self.node.save()

        ret = self.put_json('/nodes/%s/states/provision' % self.node.uuid,
                            {'target': states.VERBS['provide']},
                            headers={api_base.Version.string: "1.4"})
        self.assertEqual(202, ret.status_code)
        self.assertEqual(b'', ret.body)
        mock_dpa.assert_called_once_with(mock.ANY, self.node.uuid,
                                         states.VERBS['provide'],
                                         'test-topic')

    def test_inspect_already_in_progress(self):
        node = self.node
        node.provision_state = states.INSPECTING
        node.target_provision_state = states.MANAGEABLE
        node.reservation = 'fake-host'
        node.save()
        ret = self.put_json('/nodes/%s/states/provision' % node.uuid,
                            {'target': states.MANAGEABLE},
                            expect_errors=True)
        self.assertEqual(409, ret.status_code)  # Conflict

    @mock.patch.object(rpcapi.ConductorAPI, 'do_provisioning_action')
    def test_manage_from_available(self, mock_dpa):
        self.node.provision_state = states.AVAILABLE
        self.node.save()

        ret = self.put_json('/nodes/%s/states/provision' % self.node.uuid,
                            {'target': states.VERBS['manage']},
                            headers={api_base.Version.string: "1.4"})
        self.assertEqual(202, ret.status_code)
        self.assertEqual(b'', ret.body)
        mock_dpa.assert_called_once_with(mock.ANY, self.node.uuid,
                                         states.VERBS['manage'],
                                         'test-topic')

    @mock.patch.object(rpcapi.ConductorAPI, 'do_provisioning_action')
    def test_bad_requests_in_managed_state(self, mock_dpa):
        self.node.provision_state = states.MANAGEABLE
        self.node.save()

        for state in [states.ACTIVE, states.REBUILD, states.DELETED]:
            ret = self.put_json('/nodes/%s/states/provision' % self.node.uuid,
                                {'target': states.ACTIVE},
                                expect_errors=True)
            self.assertEqual(400, ret.status_code)
        self.assertEqual(0, mock_dpa.call_count)

    def test_set_console_mode_enabled(self):
        with mock.patch.object(rpcapi.ConductorAPI,
                               'set_console_mode') as mock_scm:
            ret = self.put_json('/nodes/%s/states/console' % self.node.uuid,
                                {'enabled': "true"})
            self.assertEqual(202, ret.status_code)
            self.assertEqual(b'', ret.body)
            mock_scm.assert_called_once_with(mock.ANY, self.node.uuid,
                                             True, 'test-topic')
            # Check location header
            self.assertIsNotNone(ret.location)
            expected_location = '/v1/nodes/%s/states/console' % self.node.uuid
            self.assertEqual(urlparse.urlparse(ret.location).path,
                             expected_location)

    @mock.patch.object(rpcapi.ConductorAPI, 'set_console_mode')
    def test_set_console_by_name_unsupported(self, mock_scm):
        ret = self.put_json('/nodes/%s/states/console' % self.node.name,
                            {'enabled': "true"},
                            expect_errors=True)
        self.assertEqual(404, ret.status_code)

    @mock.patch.object(rpcapi.ConductorAPI, 'set_console_mode')
    def test_set_console_by_name(self, mock_scm):
        ret = self.put_json('/nodes/%s/states/console' % self.node.name,
                            {'enabled': "true"},
                            headers={api_base.Version.string: "1.5"})
        self.assertEqual(202, ret.status_code)
        self.assertEqual(b'', ret.body)
        mock_scm.assert_called_once_with(mock.ANY, self.node.uuid,
                                             True, 'test-topic')

    def test_set_console_mode_disabled(self):
        with mock.patch.object(rpcapi.ConductorAPI,
                               'set_console_mode') as mock_scm:
            ret = self.put_json('/nodes/%s/states/console' % self.node.uuid,
                                {'enabled': "false"})
            self.assertEqual(202, ret.status_code)
            self.assertEqual(b'', ret.body)
            mock_scm.assert_called_once_with(mock.ANY, self.node.uuid,
                                             False, 'test-topic')
            # Check location header
            self.assertIsNotNone(ret.location)
            expected_location = '/v1/nodes/%s/states/console' % self.node.uuid
            self.assertEqual(urlparse.urlparse(ret.location).path,
                             expected_location)

    def test_set_console_mode_bad_request(self):
        with mock.patch.object(rpcapi.ConductorAPI,
                               'set_console_mode') as mock_scm:
            ret = self.put_json('/nodes/%s/states/console' % self.node.uuid,
                                {'enabled': "invalid-value"},
                                expect_errors=True)
            self.assertEqual(400, ret.status_code)
            # assert set_console_mode wasn't called
            assert not mock_scm.called

    def test_set_console_mode_bad_request_missing_parameter(self):
        with mock.patch.object(rpcapi.ConductorAPI,
                               'set_console_mode') as mock_scm:
            ret = self.put_json('/nodes/%s/states/console' % self.node.uuid,
                                {}, expect_errors=True)
            self.assertEqual(400, ret.status_code)
            # assert set_console_mode wasn't called
            assert not mock_scm.called

    def test_set_console_mode_console_not_supported(self):
        with mock.patch.object(rpcapi.ConductorAPI,
                               'set_console_mode') as mock_scm:
            mock_scm.side_effect = exception.UnsupportedDriverExtension(
                                   extension='console', driver='test-driver')
            ret = self.put_json('/nodes/%s/states/console' % self.node.uuid,
                                {'enabled': "true"}, expect_errors=True)
            self.assertEqual(400, ret.status_code)
            mock_scm.assert_called_once_with(mock.ANY, self.node.uuid,
                                             True, 'test-topic')

    def test_provision_node_in_maintenance_fail(self):
        self.node.maintenance = True
        self.node.save()

        ret = self.put_json('/nodes/%s/states/provision' % self.node.uuid,
                            {'target': states.ACTIVE},
                            expect_errors=True)
        self.assertEqual(400, ret.status_code)
        self.assertTrue(ret.json['error_message'])

    @mock.patch.object(rpcapi.ConductorAPI, 'set_boot_device')
    def test_set_boot_device(self, mock_sbd):
        device = boot_devices.PXE
        ret = self.put_json('/nodes/%s/management/boot_device'
                            % self.node.uuid, {'boot_device': device})
        self.assertEqual(204, ret.status_code)
        self.assertEqual(b'', ret.body)
        mock_sbd.assert_called_once_with(mock.ANY, self.node.uuid,
                                         device, persistent=False,
                                         topic='test-topic')

    @mock.patch.object(rpcapi.ConductorAPI, 'set_boot_device')
    def test_set_boot_device_by_name(self, mock_sbd):
        device = boot_devices.PXE
        ret = self.put_json('/nodes/%s/management/boot_device'
                            % self.node.name, {'boot_device': device},
                            headers={api_base.Version.string: "1.5"})
        self.assertEqual(204, ret.status_code)
        self.assertEqual(b'', ret.body)
        mock_sbd.assert_called_once_with(mock.ANY, self.node.uuid,
                                         device, persistent=False,
                                         topic='test-topic')

    @mock.patch.object(rpcapi.ConductorAPI, 'set_boot_device')
    def test_set_boot_device_not_supported(self, mock_sbd):
        mock_sbd.side_effect = exception.UnsupportedDriverExtension(
                                  extension='management', driver='test-driver')
        device = boot_devices.PXE
        ret = self.put_json('/nodes/%s/management/boot_device'
                            % self.node.uuid, {'boot_device': device},
                            expect_errors=True)
        self.assertEqual(400, ret.status_code)
        self.assertTrue(ret.json['error_message'])
        mock_sbd.assert_called_once_with(mock.ANY, self.node.uuid,
                                         device, persistent=False,
                                         topic='test-topic')

    @mock.patch.object(rpcapi.ConductorAPI, 'set_boot_device')
    def test_set_boot_device_persistent(self, mock_sbd):
        device = boot_devices.PXE
        ret = self.put_json('/nodes/%s/management/boot_device?persistent=True'
                            % self.node.uuid, {'boot_device': device})
        self.assertEqual(204, ret.status_code)
        self.assertEqual(b'', ret.body)
        mock_sbd.assert_called_once_with(mock.ANY, self.node.uuid,
                                         device, persistent=True,
                                         topic='test-topic')

    @mock.patch.object(rpcapi.ConductorAPI, 'set_boot_device')
    def test_set_boot_device_persistent_invalid_value(self, mock_sbd):
        device = boot_devices.PXE
        ret = self.put_json('/nodes/%s/management/boot_device?persistent=blah'
                            % self.node.uuid, {'boot_device': device},
                            expect_errors=True)
        self.assertEqual('application/json', ret.content_type)
        self.assertEqual(400, ret.status_code)

    def _test_set_node_maintenance_mode(self, mock_update, mock_get, reason,
                                        node_ident, is_by_name=False):
        request_body = {}
        if reason:
            request_body['reason'] = reason

        self.node.maintenance = False
        mock_get.return_value = self.node
        if is_by_name:
            headers = {api_base.Version.string: "1.5"}
        else:
            headers = {}
        ret = self.put_json('/nodes/%s/maintenance' % node_ident,
                            request_body, headers=headers)
        self.assertEqual(202, ret.status_code)
        self.assertEqual(b'', ret.body)
        self.assertEqual(True, self.node.maintenance)
        self.assertEqual(reason, self.node.maintenance_reason)
        mock_get.assert_called_once_with(mock.ANY, node_ident)
        mock_update.assert_called_once_with(mock.ANY, mock.ANY,
                                            topic='test-topic')

    @mock.patch.object(objects.Node, 'get_by_uuid')
    @mock.patch.object(rpcapi.ConductorAPI, 'update_node')
    def test_set_node_maintenance_mode(self, mock_update, mock_get):
        self._test_set_node_maintenance_mode(mock_update, mock_get,
                                             'fake_reason', self.node.uuid)

    @mock.patch.object(objects.Node, 'get_by_uuid')
    @mock.patch.object(rpcapi.ConductorAPI, 'update_node')
    def test_set_node_maintenance_mode_no_reason(self, mock_update, mock_get):
        self._test_set_node_maintenance_mode(mock_update, mock_get, None,
                                             self.node.uuid)

    @mock.patch.object(objects.Node, 'get_by_name')
    @mock.patch.object(rpcapi.ConductorAPI, 'update_node')
    def test_set_node_maintenance_mode_by_name(self, mock_update, mock_get):
        self._test_set_node_maintenance_mode(mock_update, mock_get,
                                             'fake_reason', self.node.name,
                                             is_by_name=True)

    @mock.patch.object(objects.Node, 'get_by_name')
    @mock.patch.object(rpcapi.ConductorAPI, 'update_node')
    def test_set_node_maintenance_mode_no_reason_by_name(self, mock_update,
                                                         mock_get):
        self._test_set_node_maintenance_mode(mock_update, mock_get, None,
                                             self.node.name, is_by_name=True)
