import React from 'react';
import { Alert, Drawer, Tabs, Tag, Typography } from 'antd';

const { Title, Paragraph, Text } = Typography;

const RULES = [
  {
    t: '授权范围',
    d: '仅在您拥有管理权限、或已获得明确书面授权的设备与网络上使用本软件。禁止对未授权目标进行连接、探测或配置操作。',
  },
  {
    t: '人员要求',
    d: '操作人员应具备基本的网络运维能力，理解所执行命令的含义与影响；设备配置操作的后果由操作人及其所在单位承担。',
  },
  {
    t: '变更管理',
    d: '生产环境的任何变更须通过「配置写入」确认流程，遵循所在单位的变更管理规范与操作窗口期；严禁绕过确认流程直接批量下发。',
  },
  {
    t: '备份先行',
    d: '任何配置修改前，先使用本软件的备份功能保存当前配置；重要变更准备回滚方案。',
  },
  {
    t: '凭据管理',
    d: '设备账号密码应妥善保管，不得共享或外传；人员离岗或凭据泄露时应及时更换密码。',
  },
  {
    t: '协议选择',
    d: 'Telnet、Serial 等明文或本地通道仅限受控实验/受控环境使用；生产环境建议使用 SSH。',
  },
  {
    t: 'AI 使用边界',
    d: 'AI 生成的命令、分析与建议仅供参考，执行前必须由人工逐条复核；不得将 AI 输出用于无人值守的自动化变更。',
  },
  {
    t: '法律合规',
    d: '遵守《中华人民共和国网络安全法》《数据安全法》《个人信息保护法》等适用法律法规，以及设备厂商的许可与使用条款。',
  },
  {
    t: '禁止用途',
    d: '禁止将本软件用于未授权访问、攻击、破坏他人网络，危害国家安全、公共安全或关键信息基础设施的任何活动。',
  },
];

const DISCLAIMER = [
  {
    t: '软件性质（现状提供）',
    d: '本软件按"现状"（AS IS）提供，属于网络运维辅助工具，仍可能存在缺陷或不完整之处。使用前请在测试环境充分验证。',
  },
  {
    t: '不提供任何保证',
    d: '不保证软件的安全性、可靠性、适用性；不保证与所有网络设备（含各厂商、各版本）的兼容性；不保证运行稳定、无错误或不间断。',
  },
  {
    t: '责任免除',
    d: '在法律允许的最大范围内，作者与贡献者对因使用或无法使用本软件导致的任何直接、间接、附带、特殊或后果性损害不承担责任，包括但不限于：设备故障、配置丢失、网络中断、业务损失、数据泄露、利润损失。',
  },
  {
    t: 'AI 内容免责',
    d: 'AI 接入模块生成的命令、分析、建议由第三方大模型服务产生，不构成专业网络工程意见，可能包含错误。执行风险与后果由使用者自行承担。',
  },
  {
    t: '第三方服务',
    d: '本软件的 AI 能力依赖第三方 OpenAI 兼容 API 服务，其可用性、数据处理规则与合规责任由相应服务商承担；向 AI 服务发送配置内容前，请评估敏感信息泄露风险。',
  },
  {
    t: '用户责任',
    d: '使用者自行承担使用本软件的全部风险，并对设备操作的合法性、合规性、安全性负责；因违规使用产生的一切后果与法律责任由使用者及所在单位承担。',
  },
  {
    t: '安全建议',
    d: '仅在隔离/受控环境使用；生产环境操作前备份配置；启用审计日志；限制软件运行主机的访问权限；定期更新至最新版本。',
  },
  {
    t: '法律适用',
    d: '本声明受中华人民共和国法律管辖。软件所含开源组件遵循其各自的许可协议。本声明可能不定期更新，继续使用软件视为接受更新后的条款。',
  },
];

function TabConn() {
  return (
    <div>
      <Alert
        type="info"
        showIcon
        message="统一连接层 — 传输方式与厂商方言正交设计"
        description="同一套业务逻辑（备份/策略/AI/配置写入）跑在任意连接方式之上；新增厂商或协议只需增加一个插件。"
        style={{ marginBottom: 16 }}
      />
      <Paragraph>
        <Tag color="blue">SSH</Tag>
        主流设备默认方式，加密通道，已做老旧算法协商兼容，适合生产环境。
      </Paragraph>
      <Paragraph>
        <Tag color="orange">Telnet</Tag>
        明文协议，仅用于老旧设备开局与隔离实验网，切勿在生产环境传输真实凭据。
      </Paragraph>
      <Paragraph>
        <Tag color="purple">Serial</Tag>
        Console 口直连（USB-Console 线），用于设备无 IP、开局、救砖场景；程序须运行在插着 Console 线的机器上。
      </Paragraph>
      <Paragraph>
        <Tag color="geekblue">带外管理</Tag>
        通过独立管理网口接入（一期仍走 SSH）；Redfish/IPMI 电源级操作规划二期。
      </Paragraph>
      <Paragraph>
        <Tag color="cyan">模拟设备</Tag>
        内置类华为/DCN 命令行模拟器，零硬件体验完整流程（终端、备份、AI、配置写入）。
      </Paragraph>
    </div>
  );
}

function TabRules() {
  return (
    <div>
      <Alert
        type="success"
        showIcon
        message="使用规则 — 使用本软件即视为知悉并同意以下规则"
        style={{ marginBottom: 16 }}
      />
      {RULES.map((r, i) => (
        <Paragraph key={r.t} style={{ marginBottom: 10 }}>
          <Text strong>
            {i + 1}. {r.t}：
          </Text>
          {r.d}
        </Paragraph>
      ))}
    </div>
  );
}

function TabDisclaimer() {
  return (
    <div>
      <Alert
        type="warning"
        showIcon
        message="免责声明 — 请仔细阅读，使用本软件即表示接受全部条款"
        style={{ marginBottom: 16 }}
      />
      {DISCLAIMER.map((r) => (
        <div key={r.t} style={{ marginBottom: 12 }}>
          <Title level={5} style={{ marginBottom: 2 }}>
            {r.t}
          </Title>
          <Paragraph type="secondary" style={{ marginBottom: 0 }}>
            {r.d}
          </Paragraph>
        </div>
      ))}
      <Paragraph type="secondary" style={{ marginTop: 16, fontSize: 12 }}>
        版本 v0.2 · 本模块内容参考网络安全工具行业通行条款与开源项目免责声明框架撰写，供内部治理使用；如用于正式商用发行，请由法务复核。
      </Paragraph>
    </div>
  );
}

export default function RulesDrawer({ open, onClose }) {
  return (
    <Drawer
      title="连接方式 · 使用规则 · 免责声明"
      placement="left"
      width={520}
      open={open}
      onClose={onClose}
    >
      <Tabs
        defaultActiveKey="rules"
        items={[
          { key: 'conn', label: '连接方式', children: <TabConn /> },
          { key: 'rules', label: '使用规则', children: <TabRules /> },
          { key: 'disc', label: '免责声明', children: <TabDisclaimer /> },
        ]}
      />
    </Drawer>
  );
}
