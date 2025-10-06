// import logo from './logo.svg';
// import './App.css';

// function App() {
//   return (
//     <div className="App">
//       <header className="App-header">
//         <img src={logo} className="App-logo" alt="logo" />
//         <p>
//           Edit <code>src/App.js</code> and save to reload.
//         </p>
//         <a
//           className="App-link"
//           href="https://reactjs.org"
//           target="_blank"
//           rel="noopener noreferrer"
//         >
//           Learn React
//         </a>
//       </header>
//     </div>
//   );
// }

// export default App;
import React, { useState, useEffect } from 'react';

const API_BASE = 'http://localhost:8000/api';

const FollowupModal = ({ isOpen, onClose, onComplete, questions, sessionId, userId }) => {
  const [answers, setAnswers] = useState(['', '', '']);
  const [currentQuestionIndex, setCurrentQuestionIndex] = useState(0);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const handleAnswerChange = (value) => {
    const newAnswers = [...answers];
    newAnswers[currentQuestionIndex] = value;
    setAnswers(newAnswers);
  };

  const handleNext = () => {
    if (currentQuestionIndex < questions.length - 1) {
      setCurrentQuestionIndex(currentQuestionIndex + 1);
    }
  };

  const handlePrevious = () => {
    if (currentQuestionIndex > 0) {
      setCurrentQuestionIndex(currentQuestionIndex - 1);
    }
  };

  const handleSubmit = async () => {
    if (answers.some(answer => !answer.trim())) {
      alert('Please answer all questions before submitting.');
      return;
    }

    setIsSubmitting(true);
    
    try {
      const response = await fetch(`${API_BASE}/followup/${sessionId}/complete`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ user_id: userId, answers: answers }),
      });

      const data = await response.json();
      
      if (data.success) {
        onComplete(data);
        onClose();
      } else {
        alert(data.message || 'Failed to submit follow-up answers');
      }
    } catch (error) {
      console.error('Error submitting follow-up:', error);
      alert('Network error. Please try again.');
    } finally {
      setIsSubmitting(false);
    }
  };

  if (!isOpen) return null;

  const progress = ((currentQuestionIndex + 1) / questions.length) * 100;

  return (
    <div style={styles.modalOverlay}>
      <div style={styles.modalContent}>
        <div style={styles.modalHeader}>
          <h2 style={styles.modalTitle}>AI Follow-up Questions</h2>
          <div style={styles.progressBar}>
            <div style={{...styles.progressFill, width: `${progress}%`}}></div>
          </div>
          <p style={styles.progressText}>Question {currentQuestionIndex + 1} of {questions.length}</p>
        </div>

        <div style={styles.questionContainer}>
          <h3 style={styles.questionText}>{questions[currentQuestionIndex]}</h3>
          <textarea
            value={answers[currentQuestionIndex]}
            onChange={(e) => handleAnswerChange(e.target.value)}
            placeholder="Type your answer here..."
            rows="6"
            style={styles.textarea}
          />
        </div>

        <div style={styles.modalButtons}>
          <button 
            onClick={handlePrevious} 
            disabled={currentQuestionIndex === 0}
            style={{...styles.btnSecondary, opacity: currentQuestionIndex === 0 ? 0.5 : 1}}
          >
            Previous
          </button>
          
          {currentQuestionIndex < questions.length - 1 ? (
            <button 
              onClick={handleNext}
              disabled={!answers[currentQuestionIndex].trim()}
              style={{...styles.btnPrimary, opacity: !answers[currentQuestionIndex].trim() ? 0.5 : 1}}
            >
              Next
            </button>
          ) : (
            <button 
              onClick={handleSubmit}
              disabled={!answers[currentQuestionIndex].trim() || isSubmitting}
              style={{...styles.btnPrimary, opacity: (!answers[currentQuestionIndex].trim() || isSubmitting) ? 0.5 : 1}}
            >
              {isSubmitting ? 'Submitting...' : 'Submit Answers'}
            </button>
          )}
        </div>
      </div>
    </div>
  );
};

const WeeklyReportModal = ({ isOpen, onClose, userId }) => {
  const [startDate, setStartDate] = useState('');
  const [endDate, setEndDate] = useState('');
  const [isGenerating, setIsGenerating] = useState(false);
  const [report, setReport] = useState(null);
  const [error, setError] = useState('');

  useEffect(() => {
    if (isOpen) {
      const today = new Date();
      const lastWeek = new Date(today);
      lastWeek.setDate(today.getDate() - 7);
      
      setEndDate(today.toISOString().split('T')[0]);
      setStartDate(lastWeek.toISOString().split('T')[0]);
      setReport(null);
      setError('');
    }
  }, [isOpen]);

  const handleGenerateReport = async () => {
    if (!startDate || !endDate) {
      setError('Please select both start and end dates');
      return;
    }

    if (new Date(startDate) > new Date(endDate)) {
      setError('Start date must be before end date');
      return;
    }

    setIsGenerating(true);
    setError('');
    setReport(null);

    try {
      const response = await fetch(`${API_BASE}/reports/weekly`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          user_id: userId.toString(),
          start_date: startDate,
          end_date: endDate
        }),
      });

      const data = await response.json();

      if (data.success) {
        setReport(data);
      } else {
        setError(data.message || 'Failed to generate weekly report.');
      }
    } catch (error) {
      console.error('Error generating weekly report:', error);
      setError('Network error. Please try again.');
    } finally {
      setIsGenerating(false);
    }
  };

  if (!isOpen) return null;

  return (
    <div style={styles.modalOverlay}>
      <div style={{...styles.modalContent, maxWidth: '800px'}}>
        <div style={styles.modalHeader}>
          <h2 style={styles.modalTitle}>Weekly Report Generator</h2>
          <p style={styles.modalSubtitle}>Generate AI-powered weekly performance summary</p>
        </div>

        <div style={styles.reportFormContainer}>
          <div style={styles.dateInputs}>
            <div style={styles.formGroup}>
              <label style={styles.label}>Start Date:</label>
              <input
                type="date"
                value={startDate}
                onChange={(e) => setStartDate(e.target.value)}
                max={endDate || new Date().toISOString().split('T')[0]}
                style={styles.input}
              />
            </div>
            <div style={styles.formGroup}>
              <label style={styles.label}>End Date:</label>
              <input
                type="date"
                value={endDate}
                onChange={(e) => setEndDate(e.target.value)}
                max={new Date().toISOString().split('T')[0]}
                style={styles.input}
              />
            </div>
          </div>

          {error && (
            <div style={styles.errorMessage}>{error}</div>
          )}

          <div style={styles.reportButtons}>
            <button
              onClick={handleGenerateReport}
              disabled={isGenerating}
              style={{...styles.btnPrimary, width: '100%', opacity: isGenerating ? 0.6 : 1}}
            >
              {isGenerating ? 'Generating Report...' : 'Generate Weekly Report'}
            </button>
            <button onClick={onClose} style={{...styles.btnSecondary, width: '100%'}}>
              Close
            </button>
          </div>

          {report && (
            <div style={styles.reportContent}>
              <div style={styles.reportHeader}>
                <h3 style={styles.reportTitle}>Weekly Report</h3>
                <p style={styles.dateRange}>
                  {new Date(report.metadata.date_range.start).toLocaleDateString()} - {new Date(report.metadata.date_range.end).toLocaleDateString()}
                </p>
              </div>
              
              <div style={styles.reportText}>
                <pre style={styles.reportBody}>{report.report}</pre>
              </div>

              {report.metadata.data_summary && (
                <div style={styles.reportSummary}>
                  <h4 style={styles.summaryTitle}>Data Summary</h4>
                  <div style={styles.summaryGrid}>
                    <div style={styles.summaryItem}>
                      <span style={styles.summaryLabel}>Work Updates</span>
                      <span style={styles.summaryValue}>{report.metadata.data_summary.work_updates_count || 0}</span>
                    </div>
                    <div style={styles.summaryItem}>
                      <span style={styles.summaryLabel}>Sessions</span>
                      <span style={styles.summaryValue}>{report.metadata.data_summary.followup_sessions_count || 0}</span>
                    </div>
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

const App = () => {
  const [activeTab, setActiveTab] = useState('logbook');
  const [formData, setFormData] = useState({
    user_id: '',
    status: 'working',
    stack: '',
    task: '',
    progress: '',
    blockers: ''
  });

  const [isSubmitting, setIsSubmitting] = useState(false);
  const [showFollowup, setShowFollowup] = useState(false);
  const [showWeeklyReport, setShowWeeklyReport] = useState(false);
  const [followupData, setFollowupData] = useState(null);
  const [message, setMessage] = useState('');
  const [messageType, setMessageType] = useState('');

  const stackOptions = [
    'Frontend Development',
    'Backend Development',
    'Full Stack Development',
    'Mobile Development',
    'DevOps',
    'Data Science',
    'UI/UX Design',
    'Quality Assurance',
    'Other'
  ];

  const handleInputChange = (e) => {
    const { name, value } = e.target;
    
    if (name === 'status' && value === 'leave') {
      setFormData(prev => ({
        ...prev,
        [name]: value,
        stack: '',
        task: '',
        progress: '',
        blockers: ''
      }));
    } else {
      setFormData(prev => ({
        ...prev,
        [name]: value
      }));
    }
  };

  const handleSubmit = async () => {
    if (!formData.user_id.trim()) {
      setMessage('User ID is required');
      setMessageType('error');
      return;
    }

    if ((formData.status === 'working' || formData.status === 'wfh') && !formData.task.trim()) {
      setMessage('Task description is required when working');
      setMessageType('error');
      return;
    }

    if (formData.status !== 'leave' && !formData.stack.trim()) {
      setMessage('Please select your task stack');
      setMessageType('error');
      return;
    }

    setIsSubmitting(true);
    setMessage('');

    try {
      const response = await fetch(`${API_BASE}/work-updates`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          ...formData,
          date: new Date().toISOString().split('T')[0],
          submittedAt: new Date().toISOString()
        }),
      });

      const data = await response.json();

      if (data.success) {
        if (data.redirectToFollowup) {
          await startFollowupSession(data);
        } else {
          setMessage(data.message);
          setMessageType('success');
          setFormData({
            user_id: formData.user_id,
            status: 'working',
            stack: '',
            task: '',
            progress: '',
            blockers: ''
          });
        }
      } else {
        setMessage(data.message || 'Submission failed');
        setMessageType('error');
      }
    } catch (error) {
      console.error('Error submitting work update:', error);
      setMessage('Network error. Please try again.');
      setMessageType('error');
    } finally {
      setIsSubmitting(false);
    }
  };

  const startFollowupSession = async (workUpdateData) => {
    try {
      const response = await fetch(`${API_BASE}/followups/start`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ user_id: formData.user_id }),
      });

      const data = await response.json();

      if (data.success) {
        setFollowupData(data);
        setShowFollowup(true);
        setMessage(`Quality Score: ${workUpdateData.qualityScore}/10. Please complete follow-up questions.`);
        setMessageType('info');
      } else {
        setMessage(data.message || 'Failed to start follow-up session');
        setMessageType('error');
      }
    } catch (error) {
      console.error('Error starting follow-up:', error);
      setMessage('Failed to start follow-up session');
      setMessageType('error');
    }
  };

  const handleFollowupComplete = (data) => {
    setMessage('Follow-up completed successfully! Your work update has been saved.');
    setMessageType('success');
    setFollowupData(null);
    
    setFormData({
      user_id: formData.user_id,
      status: 'working',
      stack: '',
      task: '',
      progress: '',
      blockers: ''
    });
  };

  const handleGenerateWeeklyReport = () => {
    if (!formData.user_id.trim()) {
      setMessage('Please enter your User ID first');
      setMessageType('error');
      return;
    }
    setShowWeeklyReport(true);
  };

  return (
    <div style={styles.app}>
      <div style={styles.container}>
        <div style={styles.header}>
          <div style={styles.headerIcon}>📊</div>
          <div>
            <h1 style={styles.headerTitle}>Daily Activity Log</h1>
            <p style={styles.headerSubtitle}>Complete your daily work summary with AI-powered follow-up and weekly reports</p>
          </div>
        </div>

        <div style={styles.tabNavigation}>
          <button 
            style={{...styles.tabButton, ...(activeTab === 'logbook' ? styles.tabButtonActive : {})}}
            onClick={() => setActiveTab('logbook')}
          >
            Daily Logbook
          </button>
          <button 
            style={{...styles.tabButton, ...(activeTab === 'reports' ? styles.tabButtonActive : {})}}
            onClick={() => setActiveTab('reports')}
          >
            Weekly Reports
          </button>
        </div>

        {message && (
          <div style={{...styles.message, ...styles[`message${messageType.charAt(0).toUpperCase() + messageType.slice(1)}`]}}>
            {message}
          </div>
        )}

        {activeTab === 'logbook' && (
          <div style={styles.workForm}>
            <div style={styles.formGroup}>
              <label style={styles.label}>User ID *</label>
              <input
                type="text"
                name="user_id"
                value={formData.user_id}
                onChange={handleInputChange}
                placeholder="Enter your user ID (e.g., intern123)"
                style={styles.input}
              />
            </div>

            <div style={styles.formGroup}>
              <label style={styles.label}>Status *</label>
              <div style={styles.radioGroup}>
                {['working', 'wfh', 'leave'].map(status => (
                  <label key={status} style={{...styles.radioOption, ...(formData.status === status ? styles.radioOptionActive : {})}}>
                    <input
                      type="radio"
                      name="status"
                      value={status}
                      checked={formData.status === status}
                      onChange={handleInputChange}
                      style={styles.radioInput}
                    />
                    <span>{status === 'wfh' ? 'Work From Home' : status.charAt(0).toUpperCase() + status.slice(1)}</span>
                  </label>
                ))}
              </div>
            </div>

            {formData.status !== 'leave' && (
              <>
                <div style={styles.formGroup}>
                  <label style={styles.label}>Task Stack *</label>
                  <select
                    name="stack"
                    value={formData.stack}
                    onChange={handleInputChange}
                    style={styles.input}
                  >
                    <option value="">Select your stack...</option>
                    {stackOptions.map(option => (
                      <option key={option} value={option}>{option}</option>
                    ))}
                  </select>
                </div>

                <div style={styles.formGroup}>
                  <label style={styles.label}>Tasks Completed *</label>
                  <textarea
                    name="task"
                    value={formData.task}
                    onChange={handleInputChange}
                    placeholder="What did you accomplish today? Be specific about tasks completed..."
                    rows="4"
                    style={styles.textarea}
                  />
                </div>

                <div style={styles.formGroup}>
                  <label style={styles.label}>Challenges Faced</label>
                  <textarea
                    name="progress"
                    value={formData.progress}
                    onChange={handleInputChange}
                    placeholder="Any obstacles or difficulties encountered..."
                    rows="3"
                    style={styles.textarea}
                  />
                </div>

                <div style={styles.formGroup}>
                  <label style={styles.label}>Plans for Tomorrow</label>
                  <textarea
                    name="blockers"
                    value={formData.blockers}
                    onChange={handleInputChange}
                    placeholder="What tasks will you focus on tomorrow..."
                    rows="3"
                    style={styles.textarea}
                  />
                </div>
              </>
            )}

            <button 
              onClick={handleSubmit} 
              disabled={isSubmitting} 
              style={{...styles.submitBtn, opacity: isSubmitting ? 0.6 : 1}}
            >
              {isSubmitting ? 'Submitting...' : 'Submit Logbook'}
            </button>

            {formData.status !== 'leave' && (
              <div style={styles.infoNote}>
                <span>🤖</span>
                <span>AI follow-up questions will be generated after submission to ensure quality</span>
              </div>
            )}
          </div>
        )}

        {activeTab === 'reports' && (
          <div style={styles.reportsSection}>
            <h2 style={styles.reportsTitle}>Weekly Performance Reports</h2>
            <p style={styles.reportsSubtitle}>Generate AI-powered insights based on your daily logbook entries</p>

            <div style={styles.weeklyReportCard}>
              <h3 style={styles.cardTitle}>📈 Weekly Summary Report</h3>
              <p style={styles.cardText}>Get a comprehensive overview of your work performance and areas for improvement.</p>
              <button 
                onClick={handleGenerateWeeklyReport} 
                style={styles.generateBtn}
              >
                Generate Weekly Report
              </button>
            </div>

            <div style={styles.infoNote}>
              <span>ℹ️</span>
              <span>Reports are generated using AI analysis of your daily logbook entries. Default range is the last 7 days.</span>
            </div>
          </div>
        )}

        <footer style={styles.footer}>
          Powered by LM Studio AI | Local & Free | No API Costs
        </footer>
      </div>

      <FollowupModal
        isOpen={showFollowup}
        onClose={() => setShowFollowup(false)}
        onComplete={handleFollowupComplete}
        questions={followupData?.questions || []}
        sessionId={followupData?.sessionId}
        userId={formData.user_id}
      />

      <WeeklyReportModal
        isOpen={showWeeklyReport}
        onClose={() => setShowWeeklyReport(false)}
        userId={formData.user_id}
      />
    </div>
  );
};

const styles = {
  app: {
    minHeight: '100vh',
    background: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)',
    padding: '20px',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
  },
  container: {
    background: 'white',
    borderRadius: '20px',
    boxShadow: '0 20px 40px rgba(0, 0, 0, 0.1)',
    maxWidth: '800px',
    width: '100%',
    overflow: 'hidden',
  },
  header: {
    background: 'linear-gradient(135deg, #3b82f6 0%, #1e40af 100%)',
    color: 'white',
    padding: '30px',
    display: 'flex',
    alignItems: 'center',
    gap: '20px',
  },
  headerIcon: {
    fontSize: '3rem',
    background: 'rgba(255, 255, 255, 0.2)',
    padding: '15px',
    borderRadius: '15px',
  },
  headerTitle: {
    fontSize: '2rem',
    fontWeight: '700',
    marginBottom: '5px',
  },
  headerSubtitle: {
    opacity: 0.9,
    fontSize: '1rem',
  },
  tabNavigation: {
    background: '#f8fafc',
    borderBottom: '1px solid #e2e8f0',
    display: 'flex',
  },
  tabButton: {
    flex: 1,
    padding: '15px 20px',
    background: 'none',
    border: 'none',
    fontSize: '1rem',
    fontWeight: '600',
    color: '#64748b',
    cursor: 'pointer',
    borderBottom: '3px solid transparent',
  },
  tabButtonActive: {
    color: '#1e40af',
    borderBottomColor: '#3b82f6',
    background: 'white',
  },
  message: {
    margin: '20px 30px',
    padding: '15px 20px',
    borderRadius: '10px',
    fontWeight: '500',
    display: 'flex',
    alignItems: 'center',
    gap: '10px',
  },
  messageSuccess: {
    background: '#dcfce7',
    color: '#166534',
    borderLeft: '4px solid #22c55e',
  },
  messageError: {
    background: '#fef2f2',
    color: '#dc2626',
    borderLeft: '4px solid #ef4444',
  },
  messageInfo: {
    background: '#dbeafe',
    color: '#1d4ed8',
    borderLeft: '4px solid #3b82f6',
  },
  workForm: {
    padding: '30px',
  },
  formGroup: {
    marginBottom: '25px',
  },
  label: {
    display: 'block',
    marginBottom: '8px',
    fontWeight: '600',
    color: '#374151',
    fontSize: '0.95rem',
  },
  input: {
    width: '100%',
    padding: '12px 16px',
    border: '2px solid #e5e7eb',
    borderRadius: '10px',
    fontSize: '1rem',
    background: '#fafafa',
    boxSizing: 'border-box',
  },
  textarea: {
    width: '100%',
    padding: '12px 16px',
    border: '2px solid #e5e7eb',
    borderRadius: '10px',
    fontSize: '1rem',
    background: '#fafafa',
    resize: 'vertical',
    minHeight: '100px',
    fontFamily: 'inherit',
    lineHeight: '1.5',
    boxSizing: 'border-box',
  },
  radioGroup: {
    display: 'flex',
    gap: '20px',
    flexWrap: 'wrap',
    marginTop: '8px',
  },
  radioOption: {
    display: 'flex',
    alignItems: 'center',
    gap: '8px',
    cursor: 'pointer',
    padding: '12px 20px',
    border: '2px solid #e5e7eb',
    borderRadius: '10px',
    background: '#fafafa',
    fontWeight: '500',
  },
  radioOptionActive: {
    borderColor: '#3b82f6',
    background: '#dbeafe',
  },
  radioInput: {
    width: 'auto',
    margin: 0,
    accentColor: '#3b82f6',
  },
  submitBtn: {
    width: '100%',
    background: 'linear-gradient(135deg, #3b82f6 0%, #1e40af 100%)',
    color: 'white',
    border: 'none',
    padding: '16px 24px',
    borderRadius: '12px',
    fontSize: '1.1rem',
    fontWeight: '600',
    cursor: 'pointer',
    textTransform: 'uppercase',
    letterSpacing: '0.5px',
  },
  infoNote: {
    background: '#f0f9ff',
    border: '1px solid #bae6fd',
    borderRadius: '10px',
    padding: '15px',
    marginTop: '20px',
    display: 'flex',
    alignItems: 'center',
    gap: '10px',
    color: '#0369a1',
    fontSize: '0.9rem',
  },
  reportsSection: {
    padding: '30px',
    textAlign: 'center',
  },
  reportsTitle: {
    fontSize: '1.8rem',
    color: '#1f2937',
    marginBottom: '10px',
  },
  reportsSubtitle: {
    color: '#64748b',
    marginBottom: '30px',
    fontSize: '1.1rem',
  },
  weeklyReportCard: {
    background: 'linear-gradient(135deg, #f0f9ff 0%, #e0f2fe 100%)',
    border: '2px solid #3b82f6',
    borderRadius: '15px',
    padding: '30px',
    marginBottom: '20px',
  },
  cardTitle: {
    color: '#1e40af',
    fontSize: '1.5rem',
    marginBottom: '15px',
  },
  cardText: {
    color: '#1e3a8a',
    marginBottom: '20px',
  },
  generateBtn: {
    width: '100%',
    background: 'linear-gradient(135deg, #3b82f6 0%, #1e40af 100%)',
    color: 'white',
    border: 'none',
    padding: '16px 24px',
    borderRadius: '12px',
    fontSize: '1.1rem',
    fontWeight: '600',
    cursor: 'pointer',
    textTransform: 'uppercase',
    letterSpacing: '0.5px',
  },
  footer: {
    background: '#f8fafc',
    padding: '20px 30px',
    textAlign: 'center',
    color: '#64748b',
    fontSize: '0.85rem',
    borderTop: '1px solid #e2e8f0',
  },
  modalOverlay: {
    position: 'fixed',
    top: 0,
    left: 0,
    right: 0,
    bottom: 0,
    background: 'rgba(0, 0, 0, 0.7)',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    zIndex: 1000,
    padding: '20px',
  },
  modalContent: {
    background: 'white',
    borderRadius: '20px',
    maxWidth: '600px',
    width: '100%',
    maxHeight: '90vh',
    overflowY: 'auto',
    boxShadow: '0 25px 50px rgba(0, 0, 0, 0.2)',
  },
  modalHeader: {
    background: 'linear-gradient(135deg, #3b82f6 0%, #1e40af 100%)',
    color: 'white',
    padding: '25px',
    borderRadius: '20px 20px 0 0',
  },
  modalTitle: {
    fontSize: '1.5rem',
    marginBottom: '5px',
    fontWeight: '700',
  },
  modalSubtitle: {
    opacity: 0.9,
    fontSize: '0.9rem',
  },
  progressBar: {
    width: '100%',
    height: '8px',
    background: 'rgba(255, 255, 255, 0.3)',
    borderRadius: '4px',
    overflow: 'hidden',
    marginTop: '15px',
    marginBottom: '10px',
  },
  progressFill: {
    height: '100%',
    background: 'white',
    borderRadius: '4px',
    transition: 'width 0.3s ease',
  },
  progressText: {
    fontSize: '0.9rem',
    opacity: 0.9,
  },
  questionContainer: {
    padding: '30px',
  },
  questionText: {
    fontSize: '1.2rem',
    color: '#374151',
    marginBottom: '20px',
    lineHeight: '1.4',
  },
  modalButtons: {
    padding: '20px 30px',
    display: 'flex',
    gap: '15px',
    justifyContent: 'space-between',
    borderTop: '1px solid #e5e7eb',
  },
  btnPrimary: {
    background: 'linear-gradient(135deg, #3b82f6 0%, #1e40af 100%)',
    color: 'white',
    border: 'none',
    padding: '12px 24px',
    borderRadius: '10px',
    fontWeight: '600',
    cursor: 'pointer',
    minWidth: '120px',
  },
  btnSecondary: {
    background: '#f3f4f6',
    color: '#374151',
    border: '2px solid #e5e7eb',
    padding: '12px 24px',
    borderRadius: '10px',
    fontWeight: '600',
    cursor: 'pointer',
    minWidth: '120px',
  },
  reportFormContainer: {
    padding: '30px',
  },
  dateInputs: {
    display: 'grid',
    gridTemplateColumns: '1fr 1fr',
    gap: '20px',
    marginBottom: '20px',
  },
  errorMessage: {
    background: '#fef2f2',
    color: '#dc2626',
    padding: '12px 16px',
    borderRadius: '8px',
    borderLeft: '4px solid #ef4444',
    marginBottom: '20px',
    fontSize: '0.9rem',
  },
  reportButtons: {
    display: 'flex',
    flexDirection: 'column',
    gap: '10px',
    marginBottom: '20px',
  },
  reportContent: {
    marginTop: '30px',
    background: '#f9fafb',
    borderRadius: '12px',
    padding: '20px',
    border: '1px solid #e5e7eb',
  },
  reportHeader: {
    marginBottom: '20px',
    paddingBottom: '15px',
    borderBottom: '2px solid #e5e7eb',
  },
  reportTitle: {
    fontSize: '1.3rem',
    color: '#1f2937',
    marginBottom: '5px',
  },
  dateRange: {
    color: '#6b7280',
    fontSize: '0.9rem',
  },
  reportText: {
    marginBottom: '20px',
  },
  reportBody: {
    whiteSpace: 'pre-wrap',
    fontFamily: 'inherit',
    fontSize: '0.95rem',
    lineHeight: '1.6',
    color: '#374151',
    margin: 0,
  },
  reportSummary: {
    background: 'white',
    padding: '20px',
    borderRadius: '10px',
    border: '1px solid #e5e7eb',
  },
  summaryTitle: {
    fontSize: '1.1rem',
    color: '#1f2937',
    marginBottom: '15px',
  },
  summaryGrid: {
    display: 'grid',
    gridTemplateColumns: '1fr 1fr',
    gap: '15px',
  },
  summaryItem: {
    background: '#f9fafb',
    padding: '15px',
    borderRadius: '8px',
    display: 'flex',
    flexDirection: 'column',
    gap: '5px',
  },
  summaryLabel: {
    fontSize: '0.85rem',
    color: '#6b7280',
    fontWeight: '500',
  },
  summaryValue: {
    fontSize: '1.5rem',
    color: '#3b82f6',
    fontWeight: '700',
  },
};

export default App;