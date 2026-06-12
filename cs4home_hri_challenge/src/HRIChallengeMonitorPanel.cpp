#include "cs4home_hri_challenge/HRIChallengeMonitorPanel.hpp"

#include "pluginlib/class_list_macros.hpp"
#include "rviz_common/display_context.hpp"
#include "rviz_common/ros_integration/ros_node_abstraction_iface.hpp"

#include <QFile>
#include <QFileDialog>
#include <QHeaderView>
#include <QHBoxLayout>
#include <QMessageBox>
#include <QMetaObject>
#include <QPushButton>
#include <QTextStream>
#include <QVBoxLayout>

#include <iomanip>
#include <sstream>

namespace cs4home_hri_challenge
{

HRIChallengeMonitorPanel::HRIChallengeMonitorPanel(QWidget * parent)
: rviz_common::Panel(parent)
{
  auto * layout = new QVBoxLayout;

  current_flow_label_ = new QLabel("Current flow: -");
  current_module_label_ = new QLabel("Module: -");
  current_transition_label_ = new QLabel("Transition: -");
  current_status_label_ = new QLabel("Status: -");
  current_elapsed_label_ = new QLabel("Elapsed time: -");
  recovery_label_ = new QLabel("Recovery: inactive");

  auto * clear_button = new QPushButton("Clear");
  connect(clear_button, &QPushButton::clicked, this, [this]() {
    resetDisplay();
  });

  auto * export_button = new QPushButton("Export Table");
  connect(export_button, &QPushButton::clicked, this, [this]() {
    saveTableToFile();
  });

  auto * button_layout = new QHBoxLayout;
  button_layout->addWidget(clear_button);
  button_layout->addWidget(export_button);

  event_table_ = new QTableWidget(0, 6);
  event_table_->setHorizontalHeaderLabels(
    {"Time", "Flow", "Module", "Transition", "Status", "Elapsed (ms)"});
  event_table_->horizontalHeader()->setSectionResizeMode(QHeaderView::Stretch);
  event_table_->verticalHeader()->setVisible(false);
  event_table_->setEditTriggers(QAbstractItemView::NoEditTriggers);
  event_table_->setSelectionBehavior(QAbstractItemView::SelectRows);

  layout->addWidget(current_flow_label_);
  layout->addWidget(current_module_label_);
  layout->addWidget(current_transition_label_);
  layout->addWidget(current_status_label_);
  layout->addWidget(current_elapsed_label_);
  layout->addWidget(recovery_label_);
  layout->addLayout(button_layout);
  layout->addWidget(event_table_);
  setLayout(layout);
}

void HRIChallengeMonitorPanel::onInitialize()
{
  auto node_abstraction = getDisplayContext()->getRosNodeAbstraction().lock();
  if (!node_abstraction) {
    recovery_label_->setText("Recovery: RViz ROS node unavailable");
    return;
  }

  node_ = node_abstraction->get_raw_node();
  event_subscriber_ = node_->create_subscription<ModuleTransitionEvent>(
    "/module_transition_events",
    rclcpp::QoS(50),
    [this](const ModuleTransitionEvent::SharedPtr msg) {
      handleEvent(msg);
    });
}

void HRIChallengeMonitorPanel::handleEvent(const ModuleTransitionEvent::SharedPtr msg)
{
  QMetaObject::invokeMethod(
    this,
    [this, msg]() {
      updateEventView(*msg);
    },
    Qt::QueuedConnection);
}

void HRIChallengeMonitorPanel::updateEventView(const ModuleTransitionEvent & msg)
{
  current_flow_label_->setText(QString("Current flow: %1").arg(QString::fromStdString(msg.flow_name)));
  current_module_label_->setText(QString("Module: %1").arg(QString::fromStdString(msg.module_name)));
  current_transition_label_->setText(
    QString("Transition: %1").arg(QString::fromStdString(msg.lifecycle_transition)));
  current_status_label_->setText(QString("Status: %1").arg(statusText(msg)));
  current_elapsed_label_->setText(QString("Elapsed time: %1 ms").arg(msg.elapsed_time_ms, 0, 'f', 1));
  current_transition_label_->setStyleSheet(transitionStyle(msg));
  current_status_label_->setStyleSheet(statusStyle(msg));

  if (msg.recovery_performed) {
    recovery_label_->setText(
      QString("Recovery: %1 via %2 in %3 ms")
      .arg(msg.success ? "completed" : "failed")
      .arg(QString::fromStdString(msg.recovery_module))
      .arg(msg.elapsed_time_ms, 0, 'f', 1));
  } else if (msg.module_failed) {
    recovery_label_->setText("Recovery: module failure detected");
  }

  event_table_->insertRow(0);
  event_table_->setItem(0, 0, new QTableWidgetItem(formatTimestamp(msg.stamp)));
  event_table_->setItem(0, 1, new QTableWidgetItem(QString::fromStdString(msg.flow_name)));
  event_table_->setItem(0, 2, new QTableWidgetItem(QString::fromStdString(msg.module_name)));
  event_table_->setItem(0, 3, new QTableWidgetItem(QString::fromStdString(msg.lifecycle_transition)));
  event_table_->setItem(0, 4, new QTableWidgetItem(statusText(msg)));
  event_table_->setItem(0, 5, new QTableWidgetItem(QString::number(msg.elapsed_time_ms, 'f', 1)));
  applyRowStyle(0, msg);

  constexpr int max_rows = 200;
  while (event_table_->rowCount() > max_rows) {
    event_table_->removeRow(event_table_->rowCount() - 1);
  }
}

void HRIChallengeMonitorPanel::resetDisplay()
{
  current_flow_label_->setText("Current flow: -");
  current_module_label_->setText("Module: -");
  current_transition_label_->setText("Transition: -");
  current_status_label_->setText("Status: -");
  current_elapsed_label_->setText("Elapsed time: -");
  recovery_label_->setText("Recovery: inactive");
  current_transition_label_->setStyleSheet("");
  current_status_label_->setStyleSheet("");
  event_table_->setRowCount(0);
}

void HRIChallengeMonitorPanel::saveTableToFile()
{
  const auto file_path = QFileDialog::getSaveFileName(
    this,
    "Export HRI monitoring data",
    "hri_monitoring_events.csv",
    "CSV files (*.csv);;All files (*)");

  if (file_path.isEmpty()) {
    return;
  }

  QFile file(file_path);
  if (!file.open(QIODevice::WriteOnly | QIODevice::Text)) {
    QMessageBox::warning(
      this,
      "Export failed",
      QString("Could not write monitoring data to %1").arg(file_path));
    return;
  }

  QTextStream stream(&file);
  stream << "Field,Value\n";
  stream << escapeCsv("Current flow") << "," << escapeCsv(current_flow_label_->text()) << "\n";
  stream << escapeCsv("Module") << "," << escapeCsv(current_module_label_->text()) << "\n";
  stream << escapeCsv("Transition") << "," << escapeCsv(current_transition_label_->text()) << "\n";
  stream << escapeCsv("Status") << "," << escapeCsv(current_status_label_->text()) << "\n";
  stream << escapeCsv("Elapsed time") << "," << escapeCsv(current_elapsed_label_->text()) << "\n";
  stream << escapeCsv("Recovery") << "," << escapeCsv(recovery_label_->text()) << "\n\n";

  for (int column = 0; column < event_table_->columnCount(); ++column) {
    if (column > 0) {
      stream << ",";
    }
    const auto * header = event_table_->horizontalHeaderItem(column);
    stream << escapeCsv(header ? header->text() : QString("Column %1").arg(column));
  }
  stream << "\n";

  for (int row = 0; row < event_table_->rowCount(); ++row) {
    for (int column = 0; column < event_table_->columnCount(); ++column) {
      if (column > 0) {
        stream << ",";
      }
      const auto * item = event_table_->item(row, column);
      stream << escapeCsv(item ? item->text() : QString());
    }
    stream << "\n";
  }
}

QString HRIChallengeMonitorPanel::escapeCsv(const QString & value) const
{
  auto escaped = value;
  escaped.replace("\"", "\"\"");
  return QString("\"%1\"").arg(escaped);
}

QString HRIChallengeMonitorPanel::formatTimestamp(
  const builtin_interfaces::msg::Time & stamp) const
{
  std::ostringstream stream;
  stream << stamp.sec << "." << std::setw(9) << std::setfill('0') << stamp.nanosec;
  return QString::fromStdString(stream.str());
}

QString HRIChallengeMonitorPanel::statusText(const ModuleTransitionEvent & msg) const
{
  if (msg.recovery_performed) {
    return msg.success ? "RECOVERED" : "RECOVERY FAILED";
  }

  if (msg.module_failed) {
    return "FAILED";
  }

  return msg.success ? "SUCCESS" : "FAILURE";
}

QString HRIChallengeMonitorPanel::transitionStyle(const ModuleTransitionEvent & msg) const
{
  if (msg.recovery_performed || msg.lifecycle_transition == "recovery") {
    return "QLabel { color: #7B1FA2; font-weight: bold; }";
  }

  if (msg.lifecycle_transition == "activate") {
    return "QLabel { color: #1565C0; font-weight: bold; }";
  }

  if (msg.lifecycle_transition == "deactivate") {
    return "QLabel { color: #EF6C00; font-weight: bold; }";
  }

  return "QLabel { color: #455A64; font-weight: bold; }";
}

QString HRIChallengeMonitorPanel::statusStyle(const ModuleTransitionEvent & msg) const
{
  if (msg.recovery_performed || msg.lifecycle_transition == "recovery") {
    return msg.success ?
      "QLabel { color: #2E7D32; font-weight: bold; }" :
      "QLabel { color: #C62828; font-weight: bold; }";
  }

  if (msg.module_failed || !msg.success) {
    return "QLabel { color: #C62828; font-weight: bold; }";
  }

  return "QLabel { color: #2E7D32; font-weight: bold; }";
}

void HRIChallengeMonitorPanel::applyRowStyle(int row, const ModuleTransitionEvent & msg)
{
  QColor background("#ECEFF1");
  QColor foreground("#263238");

  if (msg.recovery_performed || msg.lifecycle_transition == "recovery") {
    background = msg.success ? QColor("#F3E5F5") : QColor("#FFEBEE");
    foreground = msg.success ? QColor("#4A148C") : QColor("#B71C1C");
  } else if (msg.lifecycle_transition == "activate") {
    background = QColor("#E3F2FD");
    foreground = QColor("#0D47A1");
  } else if (msg.lifecycle_transition == "deactivate") {
    background = QColor("#FFF3E0");
    foreground = QColor("#E65100");
  }

  if (msg.module_failed || !msg.success) {
    background = QColor("#FFEBEE");
    foreground = QColor("#B71C1C");
  }

  for (int column = 0; column < event_table_->columnCount(); ++column) {
    auto * item = event_table_->item(row, column);
    if (!item) {
      continue;
    }
    item->setBackground(background);
    item->setForeground(foreground);
  }
}

}  // namespace cs4home_hri_challenge

PLUGINLIB_EXPORT_CLASS(
  cs4home_hri_challenge::HRIChallengeMonitorPanel,
  rviz_common::Panel)
